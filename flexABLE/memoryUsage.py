# -*- coding: utf-8 -*-
"""
Created on Wed Aug 12 16:06:52 2020

@author: intgridnb-02
"""


import sys
from types import ModuleType, FunctionType
from gc import get_referents

# Custom objects know their class.
# Function objects seem to know way too much, including modules.
# Exclude modules as well.
BLACKLIST = type, ModuleType, FunctionType

def namestr(obj, namespace):
    return [name for name in namespace if namespace[name] is obj]

def getsize(obj):
    """sum size of object & members."""
    if isinstance(obj, BLACKLIST):
        raise TypeError('getsize() does not take argument of type: '+ str(type(obj)))
    seen_ids = set()
    size = 0
    maxsize = 0
    maxobj = None
    objects = [obj]
    maxname=0
    while objects:
        need_referents = []
        for obj in objects:
            if type(obj) is str: continue
            if not isinstance(obj, BLACKLIST) and id(obj) not in seen_ids:
                seen_ids.add(id(obj))
                try:
                    size += sys.getsizeof(obj)
                    if sys.getsizeof(obj) > maxsize:
                        maxsize=sys.getsizeof(obj)
                        maxobj = obj
                        maxname = namestr(obj, globals())
                except TypeError:
                    pass
                need_referents.append(obj)
        objects = get_referents(*need_referents)
    return size, maxsize, maxobj, maxname

x = getsize(example)