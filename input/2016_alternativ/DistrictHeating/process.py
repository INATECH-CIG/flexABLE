# -*- coding: utf-8 -*-
"""
Created on Thu Apr  1 13:29:34 2021

@author: intgridnb-02
"""

import pandas as pd

inputData = pd.read_csv('inputData.csv', thousands = ',', index_col=0)
inputData.index = pd.date_range('2015','2016', freq='1h', closed='left')

inputData = inputData.resample('15T').interpolate()

inputData = inputData/inputData.sum()
inputData.reset_index(drop=True, inplace=True)
inputData = inputData.append(inputData.iloc[-99:], ignore_index=True)
inputData.to_csv('HLP_HH_DE.csv')

