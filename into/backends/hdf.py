"""

Provide a unified HDF5 interface with auto open/close
of resources.

Exposes the top-level HDFFile, HDFTable as the concrete implementation
class. These have top-level unified method signatures.

This module is in the spirit of sqlalchemy, where the impl of the HDF5
driver is a dialect.

"""


from __future__ import absolute_import, division, print_function
from contextlib import contextmanager

import os
import numpy as np
import pandas as pd

from datashape.dispatch import dispatch
from into import append, discover, resource
from ..drop import drop
from ..create import create
from ..cleanup import cleanup
from ..convert import ooc_types, convert
from ..chunks import chunks

__all__ = ['HDFFile', 'HDFTable']

# provide some registration hooks for our implementations

@dispatch(object)
def pathname(f):
    """ return my pathname """
    raise NotImplementedError()


@dispatch(object)
def dialect(f):
    """ return my dialect """
    raise NotImplementedError()


@dispatch(object, object)
def get_table(f, datapath):
    """ return a table from a passed string """
    raise NotImplementedError()


class HDFFile(object):

    """ An interface to generic hdf objects

    Parameters
    ----------
    rsrc : rsrc
        a HDF resource of the File type
    datapath : str
        The name of the node in the file
    dshape : str or datashape.DataShape

    Returns
    -------
    t : HDFFile if datapath is not None
        HDFTable otherwise

    """

    def __init__(self, rsrc, datapath=None, dshape=None, **kwargs):
        self.rsrc = rsrc
        self.datapath = datapath
        self.dshape = dshape
        self.kwargs = kwargs

        # make sure our resoure is clean
        self.pathname = pathname(self.rsrc)
        cleanup(self.rsrc)

    @property
    def dialect(self):
        return dialect(self.rsrc)

    def __str__(self):
        return "{klass} [{dialect}]: [path->{path}]".format(klass=self.__class__.__name__,
                                                            dialect=self.dialect,
                                                            path=self.pathname)
    __repr__ = __str__


    @property
    def shape(self):
        """ return my datashape """
        with self as ot:
            return discover(ot)

    def __contains__(self, key):
        """ node checking """
        return full_node_path(key) in self.keys()

    def keys(self):
        """ return the keys of myself """
        ds = discover(self)
        ds = getattr(ds,'names',ds.measure.names)
        return [full_node_path(n) for n in ds ]

    def get_table(self, datapath=None):
        """
        return the specified table

        if datapath is None, then use the default datapath
        raise ValueError if this is None
        """
        datapath = datapath or self.datapath
        if datapath is None:
            raise ValueError(
                "must specify a datapath in order to access a table in a hdf store")

        return HDFTable(self, datapath)

    def create(self):
        self.rsrc = create(self.rsrc, self.pathname)
        return self.rsrc

    def cleanup(self):
        cleanup(self.rsrc)

    def __enter__(self):
        """ make sure our resource is open """
        return self.create()

    def __exit__(self, *args):
        """ make sure our resource is closed """
        self.cleanup()

    def __getitem__(self, key):
        """ provide a getitem type selector """
        return self.get_table(key)


class HDFTable(object):

    """
    an abstract table representation in an HDFile

    Parameters
    ----------
    parent : the parent HDFFile
    datapath : str name of the datapath

    """

    def __init__(self, parent, datapath, **kwargs):
        self.parent = parent
        self.datapath = datapath
        self.kwargs = kwargs

    def __str__(self):
        return "{klass} [{dialect}]: [path->{path}, datapath->{datapath}]".format(klass=self.__class__.__name__,
                                                                                  dialect=self.dialect,
                                                                                  path=self.pathname,
                                                                                  datapath=self.datapath)
    __repr__ = __str__

    @property
    def shape(self):
        """ return my datashape """
        with self as ot:
            return discover(ot)

    @property
    def dialect(self):
        return self.parent.dialect

    @property
    def pathname(self):
        return self.parent.pathname

    def __enter__(self):
        """ return the actual node in a open/close context manager """
        handle = self.parent.create()
        return get_table(handle, datapath=self.datapath, **self.kwargs)

    def __exit__(self, *args):
        """ make sure our resource is closed """
        self.parent.cleanup()

    def __getitem__(self, key):
        """ provide a getitem type selector """
        with self as ot:
            return ot[key]

@discover.register(HDFFile)
def discover_file(f):
    with f as handle:
        return discover(f.rsrc)


@discover.register(HDFTable)
def discover_table(t):
    with t as ot:
        return discover(ot)


@append.register(HDFFile, object)
def append_object_to_store(s, data, datapath=None, **kwargs):
    """ append a single object to store, must have a datapath """

    # we possible attached to the store from the original uri
    datapath = datapath or s.datapath
    if datapath is None:
        raise ValueError(
            "must specify a datapath in order to append to a hdf store")

    t = HDFTable(s, datapath)

    with t as handle:
        append(handle, data, datapath=datapath, **kwargs)
    return t


@append.register(HDFTable, object)
def append_object_to_table(t, data, **kwargs):
    """ append a single object to a table """
    with t as handle:
        append(handle, data, **kwargs)
    return t

@append.register(HDFTable, HDFTable)
def append_object_to_table(t, data, **kwargs):
    """
    append a table to another table
    we are special casing this because of the need to keep open
    the conversion iterator here at this level (if needed)

    """

    with t as t_handle:
        with data as d_handle:
            append(t_handle, d_handle, **kwargs)
    return t

@convert.register(pd.DataFrame, HDFTable, cost=3.0)
def hdftable_to_frame(t, **kwargs):
    with t as handle:
        return convert(pd.DataFrame, handle, **kwargs)

@convert.register(np.ndarray, HDFTable, cost=3.0)
def hdftable_to_ndarray(t, **kwargs):
    with t as handle:
        return convert(np.ndarray, handle, **kwargs)

@convert.register(chunks(pd.DataFrame), HDFTable, cost=3.0)
def hdftable_to_frame_chunks(t, **kwargs):
    with t as handle:
        return convert(chunks(pd.DataFrame), handle, **kwargs)

@convert.register(chunks(np.ndarray), HDFTable, cost=3.0)
def hdftable_to_ndarray_chunks(t, **kwargs):
    with t as handle:
        return convert(chunks(np.ndarray), handle, **kwargs)


@drop.register(HDFFile)
def drop_hdffile(f):
    cleanup(f)
    os.remove(f.pathname)


@drop.register(HDFTable)
def drop_hdftable(t):
    with t as handle:
        drop(handle)


@cleanup.register(HDFFile)
def cleanup_hdffile(f):
    cleanup(f.rsrc)


@cleanup.register(HDFTable)
def cleanup_hdftable(t):
    cleanup(t.parent)


def full_node_path(n):
    """ return a full node path, IOW, a leading '/' """
    return '/' + n.lstrip('/')

ooc_types |= set([HDFTable])
