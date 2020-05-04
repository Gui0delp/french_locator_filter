# -*- coding: utf-8 -*-

import os.path
import json

from qgis.core import Qgis, QgsMessageLog, QgsLocatorFilter, QgsLocatorResult, QgsRectangle, QgsPointXY, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
from qgis.gui import QgsMapTool
from qgis.PyQt.QtCore import pyqtSignal, QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication

from .resources import *
from . networkaccessmanager import NetworkAccessManager, RequestsException
from .locatorfilter_dockwidget import LocatorFilterDockWidget


class LocatorFilterPlugin:

    def __init__(self, iface):

        self.iface = iface

        self.filter = locatorFilter(self.iface)

        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'LocatorFilterPlugin_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&French Locator Filter')
        self.toolbar = self.iface.addToolBar(u'FrenchLocatorFilter')
        self.toolbar.setObjectName(u'FrenchLocatorFilter')
        self.pluginIsActive = False
        self.dockwidget = None


        self.filter.resultProblem.connect(self.show_problem)
        self.iface.registerLocatorFilter(self.filter)

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('FrenchLocatorFilter', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar."""

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def show_problem(self, err):
        self.iface.messageBar().pushWarning("French Locator Filter Error", '{}'.format(err))

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/french_locator_filter/icons/icon.svg'
        self.add_action(
            icon_path,
            text=self.tr(u'French Locator Filter'),
            callback=self.run,
            parent=self.iface.mainWindow())

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        QApplication.restoreOverrideCursor()
        self.pluginIsActive = False

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&French Filter Locator'),
                action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

        self.iface.deregisterLocatorFilter(self.filter)

    def click_check_box(self, state):
        """The function manage the event from the check box"""

        if state == Qt.Checked:
            QApplication.setOverrideCursor(Qt.CrossCursor)
            tool = CatchTool(self.iface.mapCanvas(), self.dockwidget)
        else:
            QApplication.restoreOverrideCursor()
            tool = self.active_tool

        self.iface.mapCanvas().setMapTool(tool)

    def run(self):
        """Run method that loads and starts the plugin"""

        if not self.pluginIsActive:
            self.pluginIsActive = True

            if self.dockwidget == None:
                self.dockwidget = LocatorFilterDockWidget()
                self.active_tool = self.iface.mapCanvas().mapTool()
                self.dockwidget.cb_clic_map.stateChanged.connect(self.click_check_box)

            self.dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.dockwidget)
            self.dockwidget.show()


class locatorFilter(QgsLocatorFilter):

    USER_AGENT = b'Mozilla/5.0 QGIS LocatorFilter'

    SEARCH_URL = 'https://api-adresse.data.gouv.fr/search/?limit=10&autocomplete=1&q='

    resultProblem = pyqtSignal(str)

    def __init__(self, iface):
        self.iface = iface
        super(QgsLocatorFilter, self).__init__()

    def name(self):
        return self.__class__.__name__

    def clone(self):
        return locatorFilter(self.iface)

    def displayName(self):
        return u'Géocodeur API Adresse FR'

    def prefix(self):
        return 'fra'

    def fetchResults(self, search, context, feedback):

        if len(search) < 2:
            return

        url = '{}{}'.format(self.SEARCH_URL, search)
        self.info('Search url {}'.format(url))
        nam = NetworkAccessManager()
        try:

            headers = {b'User-Agent': self.USER_AGENT}
            # use BLOCKING request, as fetchResults already has it's own thread!
            (response, content) = nam.request(url, headers=headers, blocking=True)

            if response.status_code == 200:  # other codes are handled by NetworkAccessManager
                content_string = content.decode('utf-8')
                locations = json.loads(content_string)

                #loop on features in json collection
                for loc in locations['features']: 

                    result = QgsLocatorResult()
                    result.filter = self
                    label = loc['properties']['label']
                    if loc['properties']['type'] == 'municipality':
                        # add city code to label
                        label += ' ' + loc['properties']['citycode']
                    result.displayString = '{} ({})'.format(label, loc['properties']['type'])
                    #use the json full item as userData, so all info is in it:
                    result.userData = loc
                    self.resultFetched.emit(result)

        except RequestsException as err:
            # Handle exception..
            self.info(err)
            self.resultProblem.emit('{}'.format(err))


    def triggerResult(self, result):
        self.info("UserClick: {}".format(result.displayString))
        doc = result.userData
        x = doc['geometry']['coordinates'][0]
        y = doc['geometry']['coordinates'][1]

        centerPoint = QgsPointXY(x, y)

        dest_crs = QgsProject.instance().crs()
        results_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.PostgisCrsId)
        aTransform = QgsCoordinateTransform(results_crs, dest_crs, QgsProject.instance())
        centerPointProjected = aTransform.transform(centerPoint)
        aTransform.transform(centerPoint)

        #centers to adress coordinates
        self.iface.mapCanvas().setCenter(centerPointProjected)

        # zoom policy has we don't have extent in the results  
        scale = 25000

        type_adress = doc['properties']['type']

        if type_adress == 'housenumber' : 
            scale = 2000
        elif  type_adress == 'street' :    
            scale = 5000
        elif  type_adress == 'locality' :    
            scale = 5000

        # finally zoom actually
        self.iface.mapCanvas().zoomScale(scale)
        self.iface.mapCanvas().refresh()

    def info(self, msg=""):
        QgsMessageLog.logMessage('{} {}'.format(self.__class__.__name__, msg), 'LocatorFilter', Qgis.Info)


class CatchTool(QgsMapTool):
    """Catch tool"""

    def __init__(self, canvas, dialog):
        QgsMapTool.__init__(self, canvas)
        self.canvas = canvas
        self.dialog = dialog
        self.USER_AGENT = b'Mozilla/5.0 QGIS LocatorFilter'
        self.REVERSE_URL = "https://api-adresse.data.gouv.fr/reverse/"

    def canvasReleaseEvent(self, event):
        """Get the clic from the mouss"""

        if self.dialog.cb_clic_map.isChecked():
            x = event.pos().x()
            y = event.pos().y()
            crs_project = self.canvas.mapSettings().destinationCrs()
            x_transform = QgsCoordinateTransform(
                crs_project,
                QgsCoordinateReferenceSystem(4326),
                QgsProject.instance(),
                )

            point = self.canvas.getCoordinateTransform().toMapCoordinates(x, y)
            wgs84_point = x_transform.transform(point)
            longitude = wgs84_point[0]
            latitude = wgs84_point[1]

            url = self.REVERSE_URL + '?lon=' + str(longitude) + '&lat=' + str(latitude)
            self.info('Reverse url {}'.format(url))
            nam = NetworkAccessManager()

            try:
                headers = {b'User-Agent': self.USER_AGENT}
                # use BLOCKING request, as fetchResults already has it's own thread!
                (response, content) = nam.request(url, headers=headers, blocking=True)

                if response.status_code == 200:  # other codes are handled by NetworkAccessManager
                    json_data = content.decode('utf-8')
                    dictionnary_data = json.loads(json_data)

                    if dictionnary_data['features'] != []:
                        reverse_label = dictionnary_data['features'][0]['properties']['label']
                        self.dialog.le_input_address.setText(reverse_label)
                    else:
                        self.dialog.le_input_address.setText("No address at this location...")
                        self.info("No address at this location...")

            except RequestsException as err:
                # Handle exception..
                self.info(err)
                self.resultProblem.emit('{}'.format(err))

    def info(self, msg=""):
        QgsMessageLog.logMessage('{} {}'.format(self.__class__.__name__, msg), 'LocatorFilter', Qgis.Info)
