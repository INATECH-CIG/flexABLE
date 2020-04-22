# -*- coding: utf-8 -*-
"""
Created on Mon Apr  6 16:08:43 2020

@author: intgridnb-02
"""

# =============================================================================
# Importing Libraries
# =============================================================================
import os
# =============================================================================
# String Formatting Functions 
# =============================================================================
def prRed(skk): return("\u001b[1m\u001b[4m\u001b[31m{}\033[00m" .format(skk)) 
    #def prGreen(skk): return("\033[32m {}\033[00m" .format(skk)) 
    #def prYellow(skk): return("\033[33m {}\033[00m" .format(skk)) 
    #def prLightPurple(skk): return("\033[94m {}\033[00m" .format(skk)) 
    #def prPurple(skk): return("\033[95m {}\033[00m" .format(skk)) 
    #def prCyan(skk): return("\033[96m {}\033[00m" .format(skk)) 
    #def prLightGray(skk): return("\033[97m {}\033[00m" .format(skk)) 
    #def prBlack(skk): return("\033[98m {}\033[00m" .format(skk)) 
# =============================================================================
# Path checking function
# =============================================================================
def path_check(path):
        # Create target directory & all intermediate directories if they don't exists
    if not os.path.exists(path+'/'):
        os.makedirs(path+'/')
    else:    
        pass

# =============================================================================
# The following function will define an initializer decorator    
#
# https://stackoverflow.com/questions/1389180/automatically-initialize-instance-variables
# =============================================================================
from functools import wraps
import inspect

def initializer(func):
    """
    Automatically assigns the parameters.
    >>> class process:
    ...     @initializer
    ...     def __init__(self, cmd, reachable=False, user='root'):
    ...         pass
    >>> p = process('halt', True)
    >>> p.cmd, p.reachable, p.user
    ('halt', True, 'root')
    """
    names, varargs, keywords, defaults = inspect.getargspec(func)

    @wraps(func)
    def wrapper(self, *args, **kargs):
        for name, arg in list(zip(names[1:], args)) + list(kargs.items()):
            setattr(self, name, arg)

        for name, default in zip(reversed(names), reversed(defaults)):
            if not hasattr(self, name):
                setattr(self, name, default)

        func(self, *args, **kargs)

    return wrapper

rprintShow_parameter =None
def rprint(*args):
    global rprintShow_parameter
    if rprintShow_parameter == None:
        rprintShow_parameter = input('Should detailed simulation info be printed?(Y/N): ')
        rprintShow_parameter = True if rprintShow_parameter == 'Y' else False
    if rprintShow_parameter:
        for i in args:
            print(i, end=' ', flush=True)
        print('\n',end='')        
    else:
        pass
