# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 15:59:22 2020
@author: intgridnb-02
"""
import logging
logger = logging.getLogger("flexABLE")

class Bid(object):
    """
    The bid class is intended to represent a bid object that is offered on a DA-Market
    The minimum amount of energy that could be traded is 0.1 MWh and the price could range
    between -500 €/MWh up to 3000 €/MWh. 
    This does not represent a bid block. Multiple objects of the class bid could be used to define
    a block bid, but 
    """
    def __init__(self,issuer="Not-Issued", ID="Generic", price=0, amount=0, energyPrice=0, redispatch_price=None, status=None, bidType=None, node='DefaultNode'):
        self.ID = ID
        self.issuer = issuer
        self.price = price
        self.amount = abs(amount)
        self.confirmedAmount = 0
        self.energyPrice=energyPrice
        self.node = node
        if status == None:
            self.status = "Created"
        else:
            self.status = status
        if bidType == None:
            self.bidType = "Supply" if amount > 0 else "Demand"
        else:
            self.bidType = bidType
        if redispatch_price == None:
            self.redispatch_price = price
        else:
            self.redispatch_price = redispatch_price

    def __repr__(self):
        return self.ID

    def __add__(self, other):
        try:
            return Bid(amount=(self.amount + other.amount)).amount  # handle things with value attributes
        except AttributeError:
            return Bid(amount=(self.amount + other)).amount  # but also things without
    __radd__ = __add__
    
    def confirm(self):
        self.status = "Confirmed"
        self.confirmedAmount = self.amount
        
    def partialConfirm(self, confirmedAmount=0):
        """
        

        Parameters
        ----------
        confirmedAmount : TYPE, optional
            DESCRIPTION. The default is 0.

        Returns
        -------
        None.

        """
        if confirmedAmount == 0:
            self.status = "Rejected"
            self.confirmedAmount= 0
        elif confirmedAmount < self.amount:
            self.status = "PartiallyConfirmed"
            self.confirmedAmount= confirmedAmount
        elif confirmedAmount == self.amount:
            self.status = "Confirmed"
            self.confirmedAmount = self.amount
        elif confirmedAmount > self.amount and (confirmedAmount - self.amount) > 1:
            logger.warning("For bid {}, the confirmed amount is greater than offered amount."
                            " Confirmed amount reduced to offered amount."
                            " This could eventually cause imbalance problem. Amount: {}".format(self.ID,confirmedAmount- self.amount))
            self.confirmedAmount = self.amount


            
    def reject(self):
        if 'IED' in self.ID:
            pass
        else:
            self.status = "Rejected"
            self.confirmedAmount = 0
    
    def redispatch(self, amount=0):
        self.confirmedAmount += amount