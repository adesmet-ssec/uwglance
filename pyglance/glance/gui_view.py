#!/usr/bin/env python
# encoding: utf-8
"""
The view portion of the glance GUI code. 

Created by evas Oct 2011.
Copyright (c) 2011 University of Wisconsin SSEC. All rights reserved.
"""

import sys, os.path, logging
import numpy

from PyQt4 import QtGui, QtCore

from functools import partial

from glance.gui_constants import A_CONST, B_CONST

LOG = logging.getLogger(__name__)

"""
The GUI view is pretty simple.
All it needs to do is send messages when data is changed and
accept UI updates (of both values and lock state) from the model and controller.

The GUI's most complex responsibility is keeping the user from entering
garbage data into the UI.
"""

def add_right_aligned_label(layout, text, row, column=0):
    """
    Add a label, right-aligned, to a layout that takes a row
    and column and alignment (QGridLayout).
    """
    label = QtGui.QLabel(text)
    layout.addWidget(label, row, column, QtCore.Qt.AlignRight)
    return label


class _DoubleOrNoneValidator (QtGui.QDoubleValidator) :
    """
    This validator accepts doubles like it's parent class or None.
    """
    
    def __init__(self, parent=None) :
        super(self.__class__, self).__init__(parent)
    
    def validate (self, value, pos ) :
        """
        override our parent's validate method
        """
        
        if (value == "") or (value is None) or (value == "None") :
            return (QtGui.QValidator.Acceptable, pos)
        if (value == "N") or (value == "No") or (value == "Non") :
            return (QtGui.QValidator.Intermediate, pos)
        
        return super(self.__class__, self).validate(value, pos)
    
    def fixup (self, value) :
        """
        correct the input if needed
        """
        
        ok    = False
        
        if (value == "N") or (value == "No") or (value == "Non") :
            value = QtCore.QString("None")
            ok    = True
        if (value == "") or (value == None) :
            value = QtCore.QString("")
            ok    = True
        
        value = QtCore.QString(value)
        
        if not ok :
            super(self.__class__, self).fixup(value)
    

class GlanceGUIView (QtGui.QWidget) :
    """
    The main view object that will create the gui that's visible to the user.
    
    It includes:
    
    self.userUpdateListeners    - objects that want to be notified when the user
                                  changes data in the gui
    self.lastFilePath           - the last path that was loaded on this program run,
                                  starts as './'
    
    self.epsilonWidget          - the widget that handles the input of epsilon
    self.imageSelectionDropDown - the drop down that lets the user select the type
                                  of image to be created
    self.displayButton          - the button that lets the user create a plot
    self.widgetInfo             - a dictionary of the widgets that need to be
                                  classifed by file; these are indexed in the form
                                  self.widgetInfo[file_prefix][widget_name] and
                                  include the following widget names:
            'path' - the file path text display for that file
            'load' - the load button for that file
            'variable' - the variable drop down selector for that file
            'dims' - the label to display dimensions for that file
            'attrs' - the table to display attributes for that file
            'override' - the override check box for that file
            'fillValue' - the fill value for that file
            TODO - at some point all of these should move to these constants should
                   move to the constants module
    """
    
    def __init__ (self, versionString, parent=None) :
        """
        build the various Qt controls that make up this application
        """
        
        QtGui.QWidget.__init__(self,parent)
        
        # set our title with the version string
        self.setWindowTitle(versionString)
        
        # to make Dave happy, give it an icon
        from pkg_resources import resource_filename
        self.setWindowIcon(QtGui.QIcon(resource_filename(__name__, "pass.gif")))
        
        # a place to hang onto our file specific widgets
        self.widgetInfo = { }
        
        # setup the rest of our window
        # TODO, this section is temporary, set up the tabs in a sub function?
        self.tabWidget = QtGui.QTabWidget()
        
        # add the main tab that allows for basic control
        tempWidget = QtGui.QWidget()
        tempWidget.setLayout(self._build_data_tab())
        self.tabWidget.addTab(tempWidget, "basic")
        
        # add a tab that allows more detailed, optional settings
        tempWidget = QtGui.QWidget()
        tempWidget.setLayout(self._build_settings_tab())
        self.tabWidget.addTab(tempWidget, "settings")
        
        # add a tab that allows more complex filtering options
        tempWidget = QtGui.QWidget()
        tempWidget.setLayout(self._build_filters_tab())
        self.tabWidget.addTab(tempWidget, "filters")
        
        tempLayout = QtGui.QGridLayout()
        tempLayout.addWidget(self.tabWidget)
        self.setLayout(tempLayout)
        self.setGeometry(600, 600, 625, 700)
        
        # this will represent those who want to be notified
        # when the user changes things
        self.userUpdateListeners = [ ]
        
        # we will use this to remember were the user wanted to load files from last
        # TODO, can we remember this between program runs? something like preferences?
        self.lastFilePath = './'
        
        # hang on to stats windows so they don't vanish
        self.statsWindows = { }
        self.statsCounter = 1
        
        # hang on to data display windows
        self.dataShowWindows = { }
        self.dataShowCounter = 1
    
    def _build_data_tab (self) :
        """
        built the qt controls for the basic data tab and lay them out in a grid layout
        """
        
        # create the layout and set up some of the overall record keeping
        layoutToUse = QtGui.QGridLayout()
        currentRow = 0
        
        # set up the file info for the A file
        currentRow = self._add_file_related_controls(A_CONST, layoutToUse, currentRow)
        # set up the file info for the B file
        currentRow = self._add_file_related_controls(B_CONST, layoutToUse, currentRow)
        
        # set up the epsilon input box
        add_right_aligned_label(layoutToUse, "epsilon:", currentRow)
        self.epsilonWidget = QtGui.QLineEdit()
        self.epsilonWidget.setToolTip("Maximum acceptible difference between the variable data in the two files. Leave blank or enter None for no comparison.")
        tempValidator = _DoubleOrNoneValidator(self.epsilonWidget)
        tempValidator.setBottom(0.0) # only accept positive epsilons
        tempValidator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.epsilonWidget.setValidator(tempValidator)
        self.epsilonWidget.editingFinished.connect(self.reportEpsilonChanged)
        layoutToUse.addWidget(self.epsilonWidget, currentRow, 1, 1, 2)
        
        currentRow += 1
        
        # set up the epsilon percent input box
        add_right_aligned_label(layoutToUse, "epsilon percent:", currentRow)
        self.epsilonPerWidget = QtGui.QLineEdit()
        self.epsilonPerWidget.setToolTip("Maximum acceptible difference between the variable data in terms of % of each data point in the A file. Leave blank or enter None for no comparison.")
        tempValidator = _DoubleOrNoneValidator(self.epsilonPerWidget)
        tempValidator.setBottom(0.0) # only accept positive epsilon percents
        tempValidator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.epsilonPerWidget.setValidator(tempValidator)
        self.epsilonPerWidget.editingFinished.connect(self.reportEpsilonPercentChanged)
        layoutToUse.addWidget(self.epsilonPerWidget, currentRow, 1, 1, 2)
        
        currentRow += 1
        
        # set up the drop down to allow image type selection
        add_right_aligned_label(layoutToUse, "Image Type:", currentRow)
        self.imageSelectionDropDown = QtGui.QComboBox()
        self.imageSelectionDropDown.activated.connect(self.reportImageTypeSelected)
        layoutToUse.addWidget(self.imageSelectionDropDown, currentRow, 1, 1, 2)
        
        currentRow += 1
        
        # set up a button that shows the numerical data
        self.rawDataButton = QtGui.QPushButton("Display Data")
        self.rawDataButton.clicked.connect(self.reportDisplayRawDataClicked)
        layoutToUse.addWidget(self.rawDataButton, currentRow, 1, 1, 1)
        
        # set up a button that shows stats
        self.statsButton = QtGui.QPushButton("Display Statistics")
        self.statsButton.clicked.connect(self.reportDisplayStatsClicked)
        layoutToUse.addWidget(self.statsButton, currentRow, 2, 1, 1)
        
        # set up the button at the bottom that creates plots
        self.displayButton = QtGui.QPushButton("Display Plot")
        self.displayButton.clicked.connect(self.reportDisplayPlotClicked)
        layoutToUse.addWidget(self.displayButton, currentRow, 3, 1, 2)
        
        return layoutToUse
    
    def _add_file_related_controls (self, file_prefix, grid_layout, currentRow) :
        """
        add a set of file related controls to the widget, using the
        given name prefix and grid layout and starting on "currentRow"
        
        return the index of the next empty "currentRow" after we're finished adding controls
        """
        
        # where we'll hang onto the controls we need to access later
        self.widgetInfo[file_prefix] = { }
        
        # set up the file loading control
        add_right_aligned_label(grid_layout, "File "+file_prefix+":", currentRow)
        filePath   = QtGui.QLineEdit()
        filePath.setToolTip("The currently loaded file.")
        filePath.setReadOnly(True) # this is mostly for displaying the file path, the load button selects it
        self.widgetInfo[file_prefix]['path'] = filePath
        grid_layout.addWidget(filePath, currentRow, 1, 1, 3)
        loadButton = QtGui.QPushButton("Load")
        # set some tooltip text
        loadButton.setToolTip("Load a file: glance can handle NetCDF, HDF4, HDF5, and AERI files")
        # connect the button to an action
        loadButton.clicked.connect(partial(self.selectFileToLoad, file_prefix=file_prefix))
        self.widgetInfo[file_prefix]['load'] = loadButton
        grid_layout.addWidget(loadButton, currentRow, 4)
        
        currentRow += 1
        
        # set up the drop down for the variable select
        add_right_aligned_label(grid_layout, "variable name:", currentRow, 1)
        variableSelection = QtGui.QComboBox()
        variableSelection.setDisabled(True)
        variableSelection.activated.connect(partial(self.reportVariableSelected, file_prefix=file_prefix))
        self.widgetInfo[file_prefix]['variable'] = variableSelection
        grid_layout.addWidget(variableSelection, currentRow, 2, 1, 3)
        
        currentRow += 1
        
        # set up a label to display the variable dimension information
        add_right_aligned_label(grid_layout, "data shape:", currentRow, 1)
        dimensionsLabel = QtGui.QLabel(" ")
        self.widgetInfo[file_prefix]['dims'] = dimensionsLabel
        grid_layout.addWidget(dimensionsLabel, currentRow, 2, 1, 3)
        
        currentRow += 1
        
        # set up a table to display variable attribute information
        tempAttributesTable = QtGui.QTableWidget()
        tempAttributesTable.setColumnCount(2)
        # set up the table headers
        tempAttributesTable.setHorizontalHeaderLabels(["variable attribute", "value"])
        tempAttributesTable.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.Stretch)
        tempAttributesTable.horizontalHeader().setResizeMode(1, QtGui.QHeaderView.Stretch)
        tempAttributesTable.verticalHeader().hide()
        # save the widget and put it in our layout
        self.widgetInfo[file_prefix]['attrs'] = tempAttributesTable
        grid_layout.addWidget(tempAttributesTable, currentRow, 1, 1, 4)
        
        currentRow += 1
        
        # set up a check box to override the fill value loaded from the file
        overrideFillButton = QtGui.QCheckBox("override fill value")
        overrideFillButton.setToolTip("Check to override the default fill value.")
        overrideFillButton.setDisabled(True)
        overrideFillButton.stateChanged.connect(partial(self.reportOverrideChange, file_prefix=file_prefix))
        self.widgetInfo[file_prefix]['override'] = overrideFillButton
        grid_layout.addWidget(overrideFillButton, currentRow, 1)
        
        # now set up the input of the fill value that will be used
        add_right_aligned_label(grid_layout, "fill value:", currentRow+1, 1)
        fillValue = QtGui.QLineEdit()
        fillValue.setToolTip("The fill value that will be used.")
        tempValidator = _DoubleOrNoneValidator(fillValue)
        tempValidator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        fillValue.setValidator(tempValidator)
        fillValue.setDisabled(True)
        fillValue.editingFinished.connect(partial(self.fillValueChanged, file_prefix=file_prefix))
        self.widgetInfo[file_prefix]['fillValue'] = fillValue
        grid_layout.addWidget(fillValue, currentRow+1, 2, 1, 3)
        
        currentRow += 2
        
        return currentRow
    
    def _build_settings_tab (self) :
        """
        built the basic qt controls for the settings tab and lay them out in a grid layout
        """
        
        # create the layout and set up some of the overall record keeping
        layoutToUse = QtGui.QGridLayout()
        currentRow = 0
        
        # add the drop down for selecting a custom color map
        add_right_aligned_label(layoutToUse, "Color map:", currentRow)
        self.colormapDropDown = QtGui.QComboBox()
        self.colormapDropDown.activated.connect(self.colormapSelected)
        layoutToUse.addWidget(self.colormapDropDown, currentRow, 1, 1, 2)
        
        currentRow += 1
        
        # add a check box so the user can plot geoTIFFs as rgb images
        doPlotRGB = QtGui.QCheckBox("plot multi-channel GeoTIFFs as RGB images")
        doPlotRGB.setToolTip("When plotting original images for multi-channel GeoTIFFs, plot them as RGB images regardless of the selected variable.\n" +
                             "This setting won't change how comparison images and simpler plots like histograms appear.")
        doPlotRGB.setDisabled(False)
        doPlotRGB.stateChanged.connect(self.reportPlotGeoTiffsAsRGBToggled)
        self.plotGeoTiffsAsRGB = doPlotRGB
        layoutToUse.addWidget(doPlotRGB, currentRow, 1, 1, 2)
        
        currentRow += 1
        
        # add the drop down for selecting the data display form
        add_right_aligned_label(layoutToUse, "Data Form:", currentRow)
        self.dataDisplayFormDropDown = QtGui.QComboBox()
        self.dataDisplayFormDropDown.activated.connect(self.reportDataFormSelected)
        layoutToUse.addWidget(self.dataDisplayFormDropDown, currentRow, 1, 1, 2)
        
        currentRow += 1
        
        # add a check box to constrain originals to the same range
        showOriginalsInSameRange = QtGui.QCheckBox("show original plots in same range")
        showOriginalsInSameRange.setToolTip("Check to constrain the colorbar range of the Original A and " +
                                            "Original B data plots to be the same.\nThe range will include all data in both A and B.")
        showOriginalsInSameRange.setDisabled(False)
        showOriginalsInSameRange.stateChanged.connect(self.reportOriginalsRangeToggled)
        self.useSameRangeWidget = showOriginalsInSameRange
        layoutToUse.addWidget(showOriginalsInSameRange, currentRow, 1, 1, 2)
        
        currentRow += 1
        
        # add lon/lat controls
        
        # add box to enter lon/lat epsilon
        add_right_aligned_label(layoutToUse, "lon/lat epsilon:", currentRow)
        llepsilonWidget = QtGui.QLineEdit()
        self.llepsilonWidget = llepsilonWidget
        llepsilonWidget.setToolTip("Maximum acceptible difference between the longitudes or latitudes in the two files. Leave blank or enter None for no comparison.")
        tempValidator = _DoubleOrNoneValidator(llepsilonWidget)
        tempValidator.setBottom(0.0) # only accept positive epsilons
        tempValidator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        llepsilonWidget.setValidator(tempValidator)
        llepsilonWidget.editingFinished.connect(self.reportLLEpsilonChanged)
        layoutToUse.addWidget(llepsilonWidget, currentRow, 1, 1, 2)
        
        currentRow += 1
        
        # add the lon/lat controls that are separated by file
        currentRow = self._add_lon_lat_controls(A_CONST, layoutToUse, currentRow)
        currentRow = self._add_lon_lat_controls(B_CONST, layoutToUse, currentRow)
        
        return layoutToUse

    def _build_filters_tab (self) :
        """
        built the basic qt controls for the filters tab and lay them out in a grid layout
        """
        
        # create the layout and set up some of the overall record keeping
        layoutToUse = QtGui.QGridLayout()
        currentRow = 0
        
        # add the filtering related controls
        currentRow = self._add_simple_filter_controls(A_CONST, layoutToUse, currentRow)
        currentRow = self._add_simple_filter_controls(B_CONST, layoutToUse, currentRow)
        
        return layoutToUse
    
    def _add_simple_filter_controls (self, file_prefix, grid_layout, current_row) :
        """
        Add controls for the user to enter the simple filters; simple filters
        include restricting data to a range and correcting for AWIPS types
        
        return the next free current_row number when finished adding widgets
        """
        
        # label the specific section
        tempLabel = add_right_aligned_label(grid_layout, str(file_prefix)+" simple filtering:", current_row)
        #tempLabel.setToolTip("Simple filters are applied after any complex filters are resolved.") # TODO need to specify this once there are complex filters
        tempLabel.setToolTip("Simple filters that will be applied to the data before display or analysis.")
        
        current_row += 1
        
        # add something to give range restrictions
        restrictToRangeCheckbox = QtGui.QCheckBox("restrict data to range:")
        restrictToRangeCheckbox.setToolTip("When checked data outside the entered range will be treated as the fill value.")
        restrictToRangeCheckbox.setDisabled(False)
        restrictToRangeCheckbox.stateChanged.connect(partial(self.reportRestrictRangeToggled, file_prefix=file_prefix))
        self.widgetInfo[file_prefix]["doRestrictRangeCheckbox"] = restrictToRangeCheckbox
        grid_layout.addWidget(restrictToRangeCheckbox, current_row, 1, 1, 2)
        
        current_row += 1
        
        # add the areas to enter the range boundaries
        
        # first add the min
        minRangeValue = QtGui.QLineEdit()
        minRangeValue.setToolTip("Minimum acceptable data value for " + str(file_prefix) + " data. (Leave blank or enter None for no limit.)")
        tempValidator = _DoubleOrNoneValidator(minRangeValue)
        # at some point the bottom and top of the ranges will need to be set on this validator
        # do I need to save it or can I recover it from the widget?
        tempValidator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        minRangeValue.setValidator(tempValidator)
        minRangeValue.editingFinished.connect(partial(self.reportMinRangeValChanged, file_prefix=file_prefix))
        self.widgetInfo[file_prefix]["minRangeRestriction"] = minRangeValue
        grid_layout.addWidget(minRangeValue, current_row, 1) #, 1, 2)
        
        # now a label to clarify the relationship between the entry areas
        grid_layout.addWidget(QtGui.QLabel("to"), current_row, 2)
        
        # first add the min
        maxRangeValue = QtGui.QLineEdit()
        maxRangeValue.setToolTip("Maximum acceptable data value for " + str(file_prefix) + " data. (Leave blank or enter None for no limit.)")
        tempValidator = _DoubleOrNoneValidator(maxRangeValue)
        # at some point the bottom and top of the ranges will need to be set on this validator
        # do I need to save it or can I recover it from the widget?
        tempValidator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        maxRangeValue.setValidator(tempValidator)
        maxRangeValue.editingFinished.connect(partial(self.reportMaxRangeValChanged, file_prefix=file_prefix))
        self.widgetInfo[file_prefix]["maxRangeRestriction"] = maxRangeValue
        grid_layout.addWidget(maxRangeValue, current_row, 3) #1, 1, 2)
        
        current_row += 1
        
        # add a check box to filter AWIPS data
        isAWIPSdata = QtGui.QCheckBox("correct for AWIPS data types")
        isAWIPSdata.setToolTip("AWIPS files use signed numbers to hold unsigned data. "
                               + "Check this box if you are plotting an AWIPS file and would like your data plotted in the original, unsigned form.")
        isAWIPSdata.setDisabled(False)
        isAWIPSdata.stateChanged.connect(partial(self.reportIsAWIPSToggled, file_prefix=file_prefix))
        self.widgetInfo[file_prefix]["isAWIPScheckbox"] = isAWIPSdata
        grid_layout.addWidget(isAWIPSdata, current_row, 1, 1, 2)
        
        current_row += 1
        
        return current_row
    
    def _add_lon_lat_controls (self, file_prefix, grid_layout, current_row) :
        """
        Add the longitude and latitude controls for the given file_prefix to
        the given grid_layout starting on current_row
        
        return the next free current_row number when finished adding widgets
        """
        
        # add the label so we know which file this is for
        tempLabel = add_right_aligned_label(grid_layout, file_prefix+" Navigation:", current_row)
        tempLabel.setToolTip("Navigation variables will only be used when drawing mapped plots.")
        
        current_row += 1
        
        # add drop down to select latitude
        add_right_aligned_label(grid_layout, "Latitude:", current_row, 1)
        latNameDropDown = QtGui.QComboBox()
        latNameDropDown.activated.connect(partial(self.reportLatitudeSelected, file_prefix=file_prefix))
        self.widgetInfo[file_prefix]["latName"] = latNameDropDown
        grid_layout.addWidget(latNameDropDown, current_row, 2, 1, 2)
        
        current_row += 1
        
        # add drop down to select longitude
        add_right_aligned_label(grid_layout, "Longitude:", current_row, 1)
        lonNameDropDown = QtGui.QComboBox()
        lonNameDropDown.activated.connect(partial(self.reportLongitudeSelected, file_prefix=file_prefix))
        self.widgetInfo[file_prefix]["lonName"] = lonNameDropDown
        grid_layout.addWidget(lonNameDropDown, current_row, 2, 1, 2)
        
        current_row += 1
        
        return current_row
    
    ################# start methods related to user input #################
    
    def selectFileToLoad (self, file_prefix=None) :
        """
        when the load button is pressed, let the user pick a file to load
        """
        
        # get the file from the user
        tempFilePath = QtGui.QFileDialog.getOpenFileName(self, 'Open ' + str(file_prefix) + ' file', self.lastFilePath)
        
        LOG.debug ("New " + str(file_prefix) + " file selected in GUI: " + str(tempFilePath))
        
        if (tempFilePath is not None) and (len(tempFilePath) > 0) :
            self.lastFilePath = os.path.dirname(str(tempFilePath))
        
        # let our listeners know that the user picked a file
        for listener in self.userUpdateListeners :
            listener.newFileSelected(file_prefix, tempFilePath)
    
    def reportVariableSelected (self, file_prefix=None) :
        """
        when a variable is selected for one of the files, report it to any user update listeners
        """
        
        selectionText = self.widgetInfo[file_prefix]['variable'].currentText()
        
        # let our listeners know the user selected a variable
        for listener in self.userUpdateListeners :
            listener.userSelectedVariable(file_prefix, selectionText)
    
    def reportOverrideChange (self, file_prefix=None) :
        """
        when the user checked or unchecked one of the override checkboxes, report it to user update listeners
        """
        
        # this must be recorded before we tamper with the focus, because that will
        # trigger other events that may erase this information temporarily
        shouldDoOverride = self.widgetInfo[file_prefix]['override'].isChecked()
        
        # first we need to clean up focus in case it's in one of the line-edit boxes
        self.setFocus()
        
        # let our listeners know the user changed an overload setting
        for listener in self.userUpdateListeners :
            listener.userChangedOverload(file_prefix, shouldDoOverride)
    
    def fillValueChanged (self, file_prefix=None) :
        """
        when the user edits a fill value, report it to user update listeners
        """
        
        newFillValue = self.widgetInfo[file_prefix]['fillValue'].text()
        # it's still possible for this to not be a number, so fix that
        newFillValue = self._extra_number_validation(newFillValue)
        self.widgetInfo[file_prefix]['fillValue'].setText(str(newFillValue))
        
        # let our user update listeners know the fill value changed
        for listener in self.userUpdateListeners :
            listener.userChangedFillValue(file_prefix, newFillValue)
    
    def reportEpsilonChanged (self) :
        """
        when the epsilon changes, report it to user update listeners
        """
        
        newEpsilon = self.epsilonWidget.text()
        # it's still possible for epsilon to not be a number, so fix that
        newEpsilon = self._extra_number_validation(newEpsilon)
        self.epsilonWidget.setText(str(newEpsilon))
        
        # let our user update listeners know the epsilon changed
        for listener in self.userUpdateListeners :
            listener.userChangedEpsilon(newEpsilon)
    
    def reportLLEpsilonChanged (self) :
        """
        when the lon/lat epsilon changes, report it to user update listeners
        """
        
        newLLEpsilon = self.llepsilonWidget.text()
        # it's still possible for epsilon to not be a number, so fix that
        newLLEpsilon = self._extra_number_validation(newLLEpsilon)
        self.llepsilonWidget.setText(str(newLLEpsilon))
        
        # let our user update listeners know the llepsilon changed
        for listener in self.userUpdateListeners :
            listener.userChangedLLEpsilon(newLLEpsilon)
        
    
    
    def reportEpsilonPercentChanged (self) :
        """
        when the epsilon percent changes, report it to user update listeners
        """
        
        newEpsilonPer = self.epsilonPerWidget.text()
        # it's still possible for epsilon percent to not be a number, so fix that
        newEpsilonPer = self._extra_number_validation(newEpsilonPer)
        self.epsilonPerWidget.setText(str(newEpsilonPer))
        
        # let our user update listeners know the epsilon percent changed
        for listener in self.userUpdateListeners :
            listener.userChangedEpsilonPercent(newEpsilonPer)
    
    def reportLongitudeSelected (self, file_prefix=None) :
        """
        when a longitude variable is selected for one of the files, report it to any user update listeners
        """
        
        selectionText = self.widgetInfo[file_prefix]['lonName'].currentText()
        
        # let our listeners know the user selected a longitude
        for listener in self.userUpdateListeners :
            listener.userSelectedLongitude(file_prefix, selectionText)
    
    def reportLatitudeSelected (self, file_prefix=None) :
        """
        when a latitude variable is selected for one of the files, report it to any user update listeners
        """
        
        selectionText = self.widgetInfo[file_prefix]['latName'].currentText()
        
        # let our listeners know the user selected a latitude
        for listener in self.userUpdateListeners :
            listener.userSelectedLatitude(file_prefix, selectionText)
    
    def reportImageTypeSelected (self) :
        """
        the user selected a new image type, so let our user update listeners know that
        """
        
        newImageType = self.imageSelectionDropDown.currentText()
        
        # report the new image type to our user update listeners
        for listener in self.userUpdateListeners :
            listener.userSelectedImageType(newImageType)
    
    def colormapSelected (self) :
        """
        the user selected a colormap, let our user update listeners know
        """
        
        newColormap = self.colormapDropDown.currentText()
        
        # let the listeners know
        for listener in self.userUpdateListeners :
            listener.userSelectedColormap(newColormap)
    
    def reportDataFormSelected (self) :
        """
        the user selected a new data form, so let our user update listeners know that
        """
        
        newDataForm = self.dataDisplayFormDropDown.currentText()
        
        # report the new data form to our user update listeners
        for listener in self.userUpdateListeners :
            listener.userSelectedDataForm(newDataForm)
    
    def reportOriginalsRangeToggled (self) :
        """
        the user toggled whether or not they want their original plots to be
        displayed in a shared range
        """
        
        # this must be recorded before we tamper with the focus, because that will
        # trigger other events that may erase this information temporarily
        shouldUseSharedRange = self.useSameRangeWidget.isChecked()
        
        # first we need to clean up focus in case it's in one of the line-edit boxes
        self.setFocus()
        
        # let our listeners know the user changed an overload setting
        for listener in self.userUpdateListeners :
            listener.userToggledSharedRange(shouldUseSharedRange)
    
    def reportPlotGeoTiffsAsRGBToggled (self) :
        """
        the user toggled whether or not they want their original plots to be
        displayed in a shared range
        """
        
        # this must be recorded before we tamper with the focus, because that will
        # trigger other events that may erase this information temporarily
        doPlotRGB = self.plotGeoTiffsAsRGB.isChecked()
        
        # first we need to clean up focus in case it's in one of the line-edit boxes
        self.setFocus()
        
        # let our listeners know the user changed an overload setting
        for listener in self.userUpdateListeners :
            listener.userToggledGeoTiffAsRGB(doPlotRGB)
    
    def reportHideInvalidNavToggled (self) :
        """
        the user toggled whether or not they want the data corresponding
        with navigation that's "too different" to be hidden
        """
        
        # this must be recorded before we tamper with the focus, because that will
        # trigger other events that may erase this information temporarily
        shouldHideMismatchedNav = self.hideInvalidNavWidget.isChecked()
        
        # first we need to clean up focus in case it's in one of the line-edit boxes
        self.setFocus()
        
        # let our listeners know the user changed an overload setting
        for listener in self.userUpdateListeners :
            listener.userToggledHideMismatchedNav(shouldHideMismatchedNav)
    
    def reportRestrictRangeToggled (self, file_prefix=None) :
        """
        the user toggled the "restrict data to range" check box
        """
        
        # this must be recorded before we tamper with the focus, because that will
        # trigger other events that may erase this information temporarily
        shouldRestrictRange = self.widgetInfo[file_prefix]["doRestrictRangeCheckbox"].isChecked()
        
        # first we need to clean up focus in case it's in one of the line-edit boxes
        self.setFocus()
        
        # let our listeners know the user changed an overload setting
        for listener in self.userUpdateListeners :
            listener.userToggledRestrictRange(file_prefix, shouldRestrictRange)
    
    def reportMinRangeValChanged (self, file_prefix=None) :
        """
        the user changed the minimum value for the acceptable range
        """
        
        newRangeMin = self.widgetInfo[file_prefix]["minRangeRestriction"].text()
        # it's still possible for this to not be a number, so fix that
        newRangeMin = self._extra_number_validation(newRangeMin)
        self.widgetInfo[file_prefix]["minRangeRestriction"].setText(str(newRangeMin))
        
        # let our user update listeners know the value changed
        for listener in self.userUpdateListeners :
            listener.userChangedRangeMin(file_prefix, newRangeMin)
    
    def reportMaxRangeValChanged (self, file_prefix=None) :
        """
        the user changed the maximum value for the acceptable range
        """
        
        newRangeMax = self.widgetInfo[file_prefix]["maxRangeRestriction"].text()
        # it's still possible for this to not be a number, so fix that
        newRangeMax = self._extra_number_validation(newRangeMax)
        self.widgetInfo[file_prefix]["maxRangeRestriction"].setText(str(newRangeMax))
        
        # let our user update listeners know the value changed
        for listener in self.userUpdateListeners :
            listener.userChangedRangeMax(file_prefix, newRangeMax)
    
    def reportIsAWIPSToggled (self, file_prefix=None) :
        """
        the user toggled the "correct for AWIPS data types" check box
        """
        
        # this must be recorded before we tamper with the focus, because that will
        # trigger other events that may erase this information temporarily
        dataIsAWIPS = self.widgetInfo[file_prefix]["isAWIPScheckbox"].isChecked()
        
        # first we need to clean up focus in case it's in one of the line-edit boxes
        self.setFocus()
        
        # let our listeners know the user changed an overload setting
        for listener in self.userUpdateListeners :
            listener.userToggledIsAWIPS(file_prefix, dataIsAWIPS)
    
    def reportDisplayStatsClicked (self) :
        """
        the user clicked the display stats button
        """
        
        # make sure the focus isn't in a line-edit box
        self.statsButton.setFocus()
        
        # now report to our listeners that the user wants stats
        for listener in self.userUpdateListeners :
            listener.userRequestsStats()
    
    def reportDisplayRawDataClicked (self) :
        """
        the user clicked the display raw data button
        """
        
        # make sure the focus isn't in a line-edit box
        self.rawDataButton.setFocus()
        
        for listener in self.userUpdateListeners :
            listener.userRequestsRawData()
    
    def reportDisplayPlotClicked (self) :
        """
        the user clicked the display plot button
        """
        
        # first we need to clean up focus in case it's in one of the line-edit boxes
        self.displayButton.setFocus()
        
        # now report to our listeners that the user wants a plot
        for listener in self.userUpdateListeners :
            listener.userRequestsPlot()
    
    def _extra_number_validation (self, string_that_should_be_a_number) :
        """
        try to validate the string that should be a number
        """
        
        toReturn = None
        
        if toReturn != "" :
            try :
                toReturn = int(string_that_should_be_a_number)
            except ValueError :
                try :
                    toReturn = float(string_that_should_be_a_number)
                except ValueError :
                    pass # in this case we can't convert it, so just toss it
        
        return toReturn
    
    #################     end methods related to user input   #################
    
    ################# start data model update related methods #################
    
    def displayStatsData (self, aVariableName, bVariableName, statsAnalysis) :
        """
        given the names of the two variables and the statistical analysis,
        display this to the user
        """
        
        tempID             = self.statsCounter
        self.statsCounter += self.statsCounter + 1
        
        # I don't like this solution, but it would allow me to show multiple sets of stats at a time
        self.statsWindows[tempID] = StatisticsDisplayWindow(tempID,
                                                            aVariableName, variable_name_b=bVariableName,
                                                            statsTextToDisplay=statsAnalysis, stored_in=self.statsWindows)
    
    def displayVarData (self, variableName, fileDescriptor, variableDataObject) :
        """
        given variable data, pop a window to show it to the user
        """

        if len(variableDataObject.data.shape) == 0:
            # This is a simple scalar value. Toss it into an array
            # so the following code can cope
            newData = variableDataObject.copy()
            newData.data = numpy.array([variableDataObject.data.item()])
            variableDataObject = newData


        if len(variableDataObject.data.shape) > 0 and len(variableDataObject.data.shape) <= 2 :

            tempID                = self.dataShowCounter
            self.dataShowCounter += 1

            # not the best solution ever, but it works for now
            self.dataShowWindows[tempID] = RawDataDisplayWindow(tempID,
                                                                variableDataObject, variableName,
                                                                file_descriptor=fileDescriptor,
                                                                stored_in=self.dataShowWindows)
        else:

            LOG.debug("Unable to display data for variable " + variableName + " because it's shape of "
                      + str(variableDataObject.data.shape) + " will not work in display window.")
    
    def fileDataUpdate (self, file_prefix, file_path, selected_variable, use_fill_override, new_fill_value, variable_dimensions,
                        variable_list=None, attribute_list=None) :
        """
        The file data for one of the two files has changed. Update the GUI to reflect the change in data.
        """
        
        # set the path
        self.widgetInfo[file_prefix]['path'].setText(file_path)
        
        # if we got a new variable list, set up the appropriate drop down list
        if variable_list is not None :
            # set up the list of selectable variables for analysis
            self.widgetInfo[file_prefix]['variable'].clear()
            self.widgetInfo[file_prefix]['variable'].addItems(variable_list)
        
        # set the selected variable
        tempPosition = self.widgetInfo[file_prefix]['variable'].findText(selected_variable)
        self.widgetInfo[file_prefix]['variable'].setCurrentIndex(tempPosition)
        
        # set the override
        self.widgetInfo[file_prefix]['override'].setChecked(use_fill_override)
        
        # set the fill value that's going to be used
        self.widgetInfo[file_prefix]['fillValue'].setText(str(new_fill_value))
        
        # show the variable dimensions
        self.widgetInfo[file_prefix]['dims'].setText(str(variable_dimensions))
        
        # if needed, show the attribute list
        if attribute_list is not None :
            temp_table = self.widgetInfo[file_prefix]['attrs']
            temp_table.clearContents()
            temp_table.setRowCount(len(attribute_list.keys()))
            rowCounter = 0
            for attributeKey in sorted(attribute_list.keys()) :
                temp_table.setCellWidget(rowCounter, 0, QtGui.QLabel(str(attributeKey)))
                temp_table.setCellWidget(rowCounter, 1, QtGui.QLabel(str(attribute_list[attributeKey])))
                rowCounter += 1
        
        # if there is a file selected, enable some of the other controls
        if file_path != "" :
            self.widgetInfo[file_prefix]['variable'].setDisabled(False)
            self.widgetInfo[file_prefix]['override'].setDisabled(False)
            self.widgetInfo[file_prefix]['fillValue'].setDisabled(not use_fill_override)
    
    def updateSelectedLatLon(self, filePrefix, newLatitude, newLongitude, lonlatList=None) :
        """
        Update the latitude and longitude names that are selected in the drop down,
        if a list is given, then replace the list of options that are being displayed for that file.
        """
        
        # if we got a new list, set up the appropriate drop down lists
        if lonlatList is not None :
            
            # set up the longitude and latitude selectors
            self.widgetInfo[filePrefix]['latName'].clear()
            self.widgetInfo[filePrefix]['latName'].addItems(lonlatList)
            self.widgetInfo[filePrefix]['lonName'].clear()
            self.widgetInfo[filePrefix]['lonName'].addItems(lonlatList)
        
        # set the selected latitude
        tempPosition = self.widgetInfo[filePrefix]['latName'].findText(newLatitude)
        self.widgetInfo[filePrefix]['latName'].setCurrentIndex(tempPosition)
        
        # set the selected longitude
        tempPosition = self.widgetInfo[filePrefix]['lonName'].findText(newLongitude)
        self.widgetInfo[filePrefix]['lonName'].setCurrentIndex(tempPosition)
        
    
    def updateEpsilon (self, epsilon) :
        """
        update the comparison epsilon displayed to the user
        """
        
        #stringToUse = str(epsilon) if epsilon is not None else ""
        
        self.epsilonWidget.setText(str(epsilon))
    
    def updateEpsilonPercent (self, epsilonPercent) :
        """
        update the epsilon percent displayed to the user
        """
        
        self.epsilonPerWidget.setText(str(epsilonPercent))
    
    def updateLLEpsilon (self, newLonLatEpsilon) :
        """
        update the epsilon for longitude and latitude displayed to the user
        """
        
        self.llepsilonWidget.setText(str(newLonLatEpsilon))
    
    def updateImageTypes (self, imageType, list=None) :
        """
        update the image type that's selected,
        if the list is given, clear and reset the list of possible image types
        """
        
        # replace the list if needed
        if list is not None :
            self.imageSelectionDropDown.clear()
            self.imageSelectionDropDown.addItems(list)
        
        # change the currently selected image type
        tempPosition = self.imageSelectionDropDown.findText(imageType)
        self.imageSelectionDropDown.setCurrentIndex(tempPosition)
    
    def updateColormaps(self, colormap, list=None) :
        """
        update the colormap that's selected,
        if the list is given, clear and reset the list of possible colormaps
        """
        
        # replace the list if needed
        if list is not None :
            self.colormapDropDown.clear()
            self.colormapDropDown.addItems(list)
        
        #change the currently selected colormap
        tempPosition = self.colormapDropDown.findText(colormap)
        self.colormapDropDown.setCurrentIndex(tempPosition)
    
    def updateDataForms(self, dataForm, list=None) :
        """
        update the data form that's selected,
        if the list is given, clear and reset the list of possible data forms
        """
        
        # replace the list if needed
        if list is not None :
            self.dataDisplayFormDropDown.clear()
            self.dataDisplayFormDropDown.addItems(list)
        
        # change the currently selected data form
        tempPosition = self.dataDisplayFormDropDown.findText(dataForm)
        self.dataDisplayFormDropDown.setCurrentIndex(tempPosition)
    
    def updateUseSharedRange(self, doUseSharedRange) :
        """
        update whether or not a shared range should be used
        """
        
        self.useSameRangeWidget.setChecked(doUseSharedRange)
    
    def updatePlotGeoTiffAsRGB (self, doPlotGeoTiffAsRGB) :
        """
        update whether or not to plot geotiffs as rgb images
        """
        
        self.plotGeoTiffsAsRGB.setChecked(doPlotGeoTiffAsRGB)
    
    def updateDoRestrictRange (self, filePrefix, doRestrictRange) :
        """
        update our control to reflect whether or not the range is going to be restricted
        """
        
        self.widgetInfo[filePrefix]["doRestrictRangeCheckbox"].setChecked(doRestrictRange)
    
    def updateRestrictRangeMin (self, filePrefix, newRangeMin) :
        """
        update the minimum for the range restriction
        """
        
        self.widgetInfo[filePrefix]["minRangeRestriction"].setText(str(newRangeMin))
    
    def updateRestrictRangeMax (self, filePrefix, newRangeMax) :
        """
        update the maximum for the range restriction
        """
        
        self.widgetInfo[filePrefix]["maxRangeRestriction"].setText(str(newRangeMax))
    
    def updateIsAWIPS (self, filePrefix, isAWIPS) :
        """
        update whether or not this should be treated as an AWIPS file
        """
        
        self.widgetInfo[filePrefix]["isAWIPScheckbox"].setChecked(isAWIPS)
    
    ################# end data model update related methods #################
    
    def showWarning (self, warningMessage):
        """
        show the user a warning dialog to the user
        """
        
        tempMessageBox = QtGui.QMessageBox()
        tempMessageBox.setText(warningMessage)
        tempMessageBox.exec_()
    
    def registerUserUpdateListener (self, objectToRegister) :
        """
        add the given object to our list of listeners
        """
        
        if objectToRegister not in self.userUpdateListeners :
            self.userUpdateListeners.append(objectToRegister)

class StatisticsDisplayWindow (QtGui.QWidget) :
    """
    This class represents a window that displays a statistics comparison between two variables.
    This window is intended to be displayed in a non-modal manner.
    """
    
    def __init__ (self, id_number, variable_name_a, variable_name_b=None,
                  statsTextToDisplay="", stored_in=None, parent=None) :
        """
        set up a window to display stats
        """
        
        QtGui.QWidget.__init__(self, parent)
        
        self.id     = id_number
        self.stored = stored_in
        
        # build and set the window title
        tempTitle = "Statistics Comparing " + str(variable_name_a)
        if (variable_name_b is not None) and (variable_name_b != variable_name_a) :
            tempTitle = tempTitle + " / " + str(variable_name_b)
        tempTitle = tempTitle + " data"
        self.setWindowTitle(tempTitle)
        
        # create the layout and set up some of the overall record keeping
        layoutToUse = QtGui.QGridLayout()
        
        # set up the box that shows the stats
        self.statsText = QtGui.QTextEdit()
        self.statsText.setHtml(statsTextToDisplay)
        self.statsText.setReadOnly(True)
        layoutToUse.addWidget(self.statsText, 1, 1)
        
        # set up the overall window geometry
        self.setLayout(layoutToUse)
        self.setGeometry(400, 400, 500, 500)
        
        self.show()
    
    def closeEvent (self, event) :
        """
        we need to clean some stuff up when the window wants to close
        """
        
        if self.stored is not None :
            del self.stored[self.id]
        
        event.accept()

class NumpyArrayTableModel (QtCore.QAbstractTableModel) :
    """
    this is a model designed to show numpy arrays in
    QTableView widgets
    """
    
    def __init__(self, array_to_show, parent=None):
        """
        given the data to show, build our model
        """
        
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.np_array = array_to_show

    def rowCount(self, parent=None):
        return self.np_array.shape[0]

    def columnCount(self, parent=None):
        to_return = 1
        if len(self.np_array.shape) > 1 :
            to_return = self.np_array.shape[1]

        return to_return

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if index.isValid():
            if role == QtCore.Qt.DisplayRole:
                row = index.row()
                col = index.column()
                if len(self.np_array.shape) > 1 :
                    return QtCore.QVariant("%.5f"%self.np_array[row, col])
                else :
                    return QtCore.QVariant("%.5f"%self.np_array[row])

        return QtCore.QVariant()

class RawDataDisplayWindow (QtGui.QWidget) :
    def __init__ (self, id_number, data_object_to_display, variable_name,
                  file_descriptor=None, stored_in=None, parent=None) :
        """
        set up a window to display raw data
        """
        
        QtGui.QWidget.__init__(self, parent)
        
        self.id     = id_number
        self.stored = stored_in
        
        # set the window title
        temp_title = "Data display for " + str(variable_name)
        temp_title = temp_title + " in file " + file_descriptor if file_descriptor is not None else temp_title
        self.setWindowTitle(temp_title)
        
        # create the layout and set up some of the overall record keeping
        layoutToUse = QtGui.QGridLayout()
        
        # create a table view to display our data
        self.dataView = QtGui.QTableView()
        self.dataView.setModel(NumpyArrayTableModel(data_object_to_display.data))
        layoutToUse.addWidget(self.dataView, 1, 1)
        
        # set up the overall window geometry
        self.setLayout(layoutToUse)
        self.setGeometry(400, 400, 500, 500)
        
        self.show()
    
    def closeEvent (self, event) :
        """
        we need to clean some stuff up when the window wants to close
        """
        
        if self.stored is not None :
            del self.stored[self.id]


if __name__=='__main__':
    import doctest
    doctest.testmod()
