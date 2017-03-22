#!/usr/bin/env python
# encoding: utf-8
"""
This module handles providing stats data to the rest of the Glance GUI.

Created by evas Nov 2011.
Copyright (c) 2011 University of Wisconsin SSEC. All rights reserved.
"""

from pkg_resources import resource_string, resource_filename
from mako.template import Template
from mako.lookup   import TemplateLookup

import glance.stats as stats
import glance.data  as dataobjects

from glance.gui_constants import A_CONST, B_CONST

import logging

LOG = logging.getLogger(__name__)

class GlanceGUIStats (object) :
    """
    this class represents a model object that manages providing
    statistics information to the Glance GUI
    
    it includes:
    
    self.dataModel      - the GlanceGUIModel object that contains the main data
                          model for the GUI
    self.statsListeners - objects that want to be notified when stats are calculated
    self.errorHandlers  - objects that want to be notified when there's a serious error
    """
    
    def __init__ (self, dataModelToSave) :
        """
        create the gui stats object, hanging onto the dataModel given
        """
        
        self.dataModel      = dataModelToSave
        self.statsListeners = [ ]
        self.errorHandlers  = [ ]
    
    def registerStatsListener (self, objectToRegister) :
        """
        add the given object to our list of stats listeners
        """
        
        if objectToRegister not in self.statsListeners :
            self.statsListeners.append(objectToRegister)
    
    def registerErrorHandler (self, objectToRegister) :
        """
        add the given object to our list of error handlers
        """
        
        if objectToRegister not in self.errorHandlers :
            self.errorHandlers.append(objectToRegister)
    
    def sendStatsInfo (self) :
        """
        our data listeners should be sent statistics information 
        for the currently selected variable or variables (if possible)
        
        may raise an IncompatableDataObjects exception if it is impossible to compare the given data
        """
        
        # get Variable names
        aVarName    = self.dataModel.getVariableName(A_CONST)
        bVarName    = self.dataModel.getVariableName(B_CONST)
        
        # get Data objects
        aDataObject = self.dataModel.getVariableData(A_CONST, aVarName)
        bDataObject = self.dataModel.getVariableData(B_CONST, bVarName)

        if aDataObject is None and bDataObject is not None:
            aDataObject, bDataObject = bDataObject, aDataObject

        if aDataObject is not None and bDataObject is None:
            return self.sendStatsInfoSingle(aVarName, aDataObject)

        return self.sendStatsInfoPair(aVarName, bVarName, aDataObject, bDataObject)

        
    def sendStatsInfoPair(self, aVarName, bVarName, aDataObject, bDataObject):
        """
        send data listeners statistics information 
        for the currently selected variables
        
        may raise an IncompatableDataObjects exception if it is impossible to compare the given data
        """
        # check the minimum validity of our data; this call can raise an IncompatableDataObjects exception
        dataobjects.DiffInfoObject.verifyDataCompatability(aDataObject, bDataObject, aVarName, bVarName)
        
        LOG.info ("Constructing statistics")
        
        # do the statistical analysis and collect the data that will be needed to render it nicely
        tempAnalysis = stats.StatisticalAnalysis.withDataObjects(aDataObject, bDataObject,
                                                                 epsilon=self.dataModel.getEpsilon(),
                                                                 epsilon_percent=self.dataModel.getEpsilonPercent())
        # TODO, these constants should be moved into the gui_constants
        tempInfo = { 'variable_name':       aVarName,
                     'alternate_name_in_B': bVarName }
        kwargs   = { 'runInfo':    tempInfo,
                     'statGroups': tempAnalysis.dictionary_form() }
        
        # use a mako template to render an html verion of the stats for display
        templateLookup = TemplateLookup(directories=[resource_filename(__name__, ".")])
        guiTemplate    = Template(resource_string(__name__, "guistatsreport.txt"), lookup=templateLookup)
        renderedText = guiTemplate.render(**kwargs)
        
        # tell my listeners to show the stats data we've collected
        for listener in self.statsListeners :
                listener.displayStatsData(aVarName, bVarName, renderedText)

    def sendStatsInfoSingle(self, aVarName, aDataObject):
        """
        send data listeners statistics information 
        for the currently selected variable
        """
        LOG.info ("Constructing statistics for one variable")

        # do the statistical analysis and collect the data that will be needed to render it nicely
        tempAnalysis = stats.StatisticalInspectionAnalysis.withDataObjects(aDataObject)
        # TODO, these constants should be moved into the gui_constants
        tempInfo = { 'variable_name': aVarName }
        kwargs   = { 'runInfo':    tempInfo,
                     'statGroups': tempAnalysis.dictionary_form() }

        # use a mako template to render an html verion of the stats for display
        templateLookup = TemplateLookup(directories=[resource_filename(__name__, ".")])
        guiTemplate    = Template(resource_string(__name__, "guistatsreport.txt"), lookup=templateLookup)
        renderedText = guiTemplate.render(**kwargs)

        # tell my listeners to show the stats data we've collected
        for listener in self.statsListeners :
                listener.displayStatsData(aVarName, None, renderedText)


    
    def sendRawData (self, fileID) :
        """
        Send raw data information to our listeners
        """
        
        # get Variable name
        varName    = self.dataModel.getVariableName(fileID)
        
        # get Data object
        dataObject = self.dataModel.getVariableData(fileID, varName)
        
        if dataObject is not None :
            # tell my listeners to show the stats data we've collected
            for listener in self.statsListeners :
                    listener.displayVarData (varName, fileID, dataObject)

