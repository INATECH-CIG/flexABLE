# -*- coding: utf-8 -*-
"""
Created on Wed Jun 24 10:34:33 2020

@author: intgridnb-02
"""
import pandas as pd
x = pd.read_csv('C:/Users/intgridnb-02/Desktop/flexABLE/input/2015_Network/PV_CF_1.csv', thousands=',').drop('hour', axis=1)
x.set_index(pd.date_range('2015', '2016', freq='H', closed='left'), inplace=True)
x= x.resample('15T').interpolate(method='linear')
#x = x.div(x.sum(axis=1),axis=0)
x.reset_index(inplace=True,drop=True)
x.fillna(0, inplace=True)
x.to_csv('C:/Users/intgridnb-02/Desktop/flexABLE/input/2015_Network/PV_CF.csv')
