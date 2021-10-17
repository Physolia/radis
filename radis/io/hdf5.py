# -*- coding: utf-8 -*-
"""
Created on Tue Jan 26 21:27:15 2021

@author: erwan
"""

import os
import sys
from os.path import exists
from time import time

import h5py
import pandas as pd
from tables.exceptions import NoSuchNodeError


def update_pytables_to_vaex(fname, remove_initial=False, verbose=True, key="df"):
    """Convert a HDF5 file generated from PyTables to a
    Vaex-friendly HDF5 format, preserving metadata"""
    import vaex

    if verbose:
        print(f"Auto-updating {fname} to a Vaex-compatible HDF5 file")
    df = pd.read_hdf(fname)
    df = vaex.from_pandas(df)
    if fname.endswith(".h5"):
        fname_vaex = fname.replace(".h5", ".hdf5")
    else:
        fname_vaex = fname

    # Read metadata
    with pd.HDFStore(fname, mode="r") as store:
        file_metadata = store.get_storer(key).attrs.metadata

    # Write Vaex file
    df.export_hdf5(fname_vaex)
    df.close()  # try to fix file not closed()  TODO: remove?
    del df  # same TODO

    with h5py.File(fname_vaex, "a") as hf:
        # Add metadata
        for k, v in file_metadata.items():
            hf.attrs[k] = v

    if verbose:
        print(f"Converted to Vaex's HDF5 format {fname_vaex}")

    if remove_initial and fname != fname_vaex:
        # Remove initial file
        os.remove(fname)
        if verbose:
            print(f"Deleting {fname}")

    return fname_vaex


class HDF5Manager(object):
    def __init__(self, engine="pytables"):
        self.engine = engine

    def open(self, file, mode="w"):
        if self.engine == "pytables":
            return pd.HDFStore(file, mode=mode, complib="blosc", complevel=9)
        elif self.engine == "vaex":
            import vaex

            return vaex.open(file)
        else:
            raise NotImplementedError(self.engine)

    def write(
        self,
        file,
        df,
        append=True,
        key=None,
        format="table",
        data_columns=["iso", "wav"],
    ):
        """Write dataframe ``df`` to ``file``

        Other Parameters
        ----------------
        data_columns : list
            only these column names will be searchable directly on disk to
            load certain lines only. See :py:func:`~radis.io.hdf5.hdf2df`
        """
        if self.engine == "pytables":
            if key is None:
                key = "df"
            df.to_hdf(
                file,
                key=key,
                mode="a" if append else "w",
                format=format,
                data_columns=data_columns,
            )
        elif self.engine == "vaex":
            if key is None:
                key = r"/table"
            import vaex

            if append == True:
                raise ValueError(
                    "Cannot append with 'vaex' engine. Load all files separately using vaex.open('many') then export to a single file"
                )
            try:
                df.export_hdf5(file, group=key, mode="a" if append else "w")
            except AttributeError:  # case where df is not a Vaex dataFrame but (likely) a Pandas Dataframe
                vaex.from_pandas(df).export_hdf5(
                    file, group=key, mode="a" if append else "w"
                )
        else:
            raise NotImplementedError(self.engine)
            # h5py is not designed to write Pandas DataFrames

    def load(self, fname, columns=None, where=None, key=None, **store_kwargs):
        """
        Parameters
        ----------
        columns: list of str
            list of columns to load. If ``None``, returns all columns in the file.
        where: list of str
            filtering conditions. Ex::

                "wav > 2300"

        Other Parameters
        ----------------
        key: store key in  ``'pytables'`` mode.

        Returns
        -------
        pd.DataFrame or vaex.DataFrame
        """

        if self.engine == "pytables":
            if key is None:
                key = "df"
            try:
                df = pd.read_hdf(
                    fname, columns=columns, where=where, key=key, **store_kwargs
                )
            except TypeError as err:
                if "reading from a Fixed format store" in str(err):
                    raise TypeError(
                        f"radis.io.hdf5.hdf2df can only be used to load specific HDF5 files generated in a 'Table' which allows to select only certain columns or rows. Here the file {fname} is in 'Fixed' format. Regenerate it ? If it's a cache file of a .par file, load the .par file directly ?"
                    )
                elif "cannot create a storer if the object is not existing" in str(err):
                    raise TypeError(
                        f"Missing group `{key}` in {fname}. Maybe the file has been generated by a different HDF5 library than Pytables. Try using `engine='vaex'` in the calling function (hdf2df, etc.)"
                    )
                else:
                    raise
            except NoSuchNodeError as err:
                # Probably tried to read a Vaex/h5py HDF5 file forcing "engine='pytables'"
                raise AttributeError(
                    f"file {fname} does not seem to have been generated by Pytables. Try using `engine='vaex'` in the calling function (hdf2df, etc.)"
                ) from err

        elif self.engine == "vaex":
            if key is None:
                key = r"/table"
            import vaex

            # Open file
            assert len(store_kwargs) == 0
            try:
                df = vaex.open(fname, group=key)
            except FileNotFoundError as err:
                # error message with suggestion on how to convert from existing file
                fname_list = fname if isinstance(fname, list) else [fname]
                for f in fname_list:
                    if exists(f.replace(".hdf5", ".h5")):
                        raise FileNotFoundError(
                            f"`{f}` not found but `{f.replace('.hdf5', '.h5')}` exists (probably a row-based pytables HDF5 file). Try (1) using engine='pytables' in the calling function (`hdf2df`, `fetch_hitemp`, etc.)  ; (2) delete the file to re-download and re-parse it (this may take a lot of time !) ;  or (3, recommended) set `import radis; radis.congig['AUTO_UPDATE_DATABASE']= True` in your script to auto-update to Vaex HDF5 file"
                        ) from err
                # else:
                raise
            except OSError as err:
                raise OSError(
                    f"Cannot read {fname}, group `{key}` with Vaex HDF5 library (column-based). It may be a file generated by pytables (row-based). Try (1) using engine='pytables' in the calling function (`hdf2df`, `fetch_hitemp`, etc.)  ; (2) delete the file to re-download and re-parse it (this may take a lot of time !) ;  or (3, recommended) set `import radis; radis.congig['AUTO_UPDATE_DATABASE'] = True` in your script to auto-update to Vaex HDF5 file"
                ) from err

            return df

        elif self.engine == "h5py":
            # TODO: define default key ?
            import h5py

            with h5py.File(fname, "r") as f:
                if key:
                    load_from = f[key]
                else:
                    load_from = f
                out = {}
                for k in load_from.keys():
                    out[k] = f[k][()]
            return pd.DataFrame(out)

        else:
            raise NotImplementedError(self.engine)

        return df

    def add_metadata(self, fname: str, metadata: dict, key=None):
        """
        Parameters
        ----------
        fname: str
            filename
        metadata: dict
            dictionary of metadata to add in group ``key``

        """
        from radis.io.cache_files import _h5_compatible

        if self.engine == "pytables":
            if key is None:
                key = "df"
            with pd.HDFStore(fname, mode="a", complib="blosc", complevel=9) as f:
                f.get_storer(key).attrs.metadata = metadata

        elif self.engine == "h5py":
            # TODO: define default key
            with h5py.File(fname, "a") as hf:
                hf.attrs.update(_h5_compatible(metadata))

        elif self.engine == "vaex":
            if key is None:
                key = r"/table"
            # Should be able to deal with multiple files at a time
            if isinstance(fname, list):
                assert isinstance(metadata, list)
                for f, m in zip(fname, metadata):
                    with h5py.File(f, "a") as hf:
                        hf.attrs.update(_h5_compatible(m))
            else:
                with h5py.File(fname, "a") as hf:
                    hf.attrs.update(_h5_compatible(metadata))

        else:
            raise NotImplementedError(self.engine)

    def read_metadata(self, fname: str, key=None) -> dict:
        """
        Other Parameters
        ----------------
        key: store key in  ``'pytables'`` mode.
        """

        if self.engine == "pytables":
            if key is None:
                key = "df"
            with pd.HDFStore(fname, mode="r", complib="blosc", complevel=9) as f:

                metadata = f.get_storer(key).attrs.metadata

        elif self.engine == "h5py":
            # TODO: define default key
            with h5py.File(fname, "r") as hf:
                metadata = dict(hf.attrs)

        elif self.engine == "vaex":
            if key is None:
                key = r"/table"
            if isinstance(fname, list):
                metadata = []
                for f in fname:
                    with h5py.File(f, "r") as hf:
                        metadata.append(dict(hf.attrs))
            else:
                with h5py.File(fname, "r") as hf:
                    metadata = dict(hf.attrs)

        else:
            raise NotImplementedError(self.engine)

        return metadata

    @classmethod
    def guess_engine(self, file, verbose=True):
        """Guess which HDF5 library ``file`` is compatible with"""
        # See if it looks like PyTables
        #  TODO : move in Manager
        with pd.HDFStore(file, mode="r") as store:
            if store.get_storer("df"):
                engine = "pytables"
            else:
                engine = "h5py"
        if verbose:
            print(f"Guessed that {file} was compatible with `{engine}` hdf5 engine")
        return engine


def hdf2df(
    fname,
    columns=None,
    isotope=None,
    load_wavenum_min=None,
    load_wavenum_max=None,
    verbose=True,
    store_kwargs={},
    engine="auto",
):
    """Load a HDF5 line databank into a Pandas DataFrame.

    Adds HDF5 metadata in ``df.attrs``

    Parameters
    ----------
    fname : str
        HDF5 file name
    columns: list of str
        list of columns to load. If ``None``, returns all columns in the file.
    isotope: str
        load only certain isotopes : ``'2'``, ``'1,2'``, etc. If ``None``, loads
        everything. Default ``None``.
    load_wavenum_min, load_wavenum_max: float (cm-1)
        load only specific wavelength.

    Other Parameters
    ----------------
    store_kwargs: dict
        arguments forwarded to :py:meth:`~pandas.io.pytables.read_hdf`
    engine: ``'h5py'``, ``'pytables'``, ``'vaex'``, ``'auto'``
        which HDF5 library to use. If ``'auto'``, try to guess. Note: ``'vaex'``
        uses ``'h5py'`` compatible HDF5.

    Returns
    -------
    df: pandas Dataframe
        dataframe containing all lines or energy levels

    Examples
    --------

    ::


        path = getDatabankEntries("HITEMP-OH")['path'][0]
        df = hdf2df(path)

        df = hdf2df(path, columns=['wav', 'int'])

        df = hdf2df(path, isotope='2')
        df = hdf2df(path, isotope='1,2)

        df = hdf2df(path, load_wavenum_min=2300, load_wavenum_max=2500)

    Notes
    -----

    DataFrame metadata in ``df.attrs`` is still experimental in Pandas and can be lost
    during ``groupby, pivot, join or loc`` operations on the Dataframe.
    See https://stackoverflow.com/questions/14688306/adding-meta-information-metadata-to-pandas-dataframe

    Always check for existence !

    """

    if engine == "auto":
        engine = HDF5Manager.guess_engine(fname)

    t0 = time()

    # Selection
    selection = False
    if engine == "pytables":
        # Selection
        selection = True
        where = []
        if load_wavenum_min is not None:
            where.append(f"wav > {load_wavenum_min}")
        if load_wavenum_max is not None:
            where.append(f"wav < {load_wavenum_max}")
        if isotope:
            where.append(f'iso in {isotope.split(",")}')

    elif engine == "vaex":
        #  Selection is done after opening the file time in vaex
        where = []
    else:
        raise NotImplementedError(engine)

    # Load :

    manager = HDF5Manager(engine)
    df = manager.load(fname, columns=columns, where=where, **store_kwargs)

    #  Selection in vaex
    if engine == "vaex":

        # Selection
        selection = True
        # limitation : so far the df.select(df.iso in isotope.split(",")) syntax
        # fails in Vaex (and worse: still returns something.)
        # For the moment, only implement with one isotope.
        # TODO : add all cases manually...
        if isotope is not None:
            if not isinstance(isotope, int):
                try:
                    isotope = int(isotope)
                except:
                    raise NotImplementedError(
                        f"When reading HDF5 in vaex mode, selection works for a single isotope only (got {isotope})"
                    )
        if (
            load_wavenum_min is not None
            and load_wavenum_max is not None
            and isotope is not None
        ):
            df.select(
                (df.wav > load_wavenum_min)
                & (df.wav < load_wavenum_max)
                & (df.iso == isotope)
            )
        elif load_wavenum_min is not None and load_wavenum_max is not None:
            df.select((df.wav > load_wavenum_min) & (df.wav < load_wavenum_max))
        elif load_wavenum_min is not None and isotope is not None:
            df.select((df.wav > load_wavenum_min) & (df.iso == isotope))
        elif load_wavenum_max is not None and isotope is not None:
            df.select((df.wav < load_wavenum_max) & (df.iso == isotope))
        elif load_wavenum_min is not None:
            df.select(df.wav > load_wavenum_min)
        elif load_wavenum_max is not None:
            df.select(df.wav < load_wavenum_max)
        elif isotope is not None:
            df.select(df.iso == isotope)
        else:
            selection = False

        # Load
        df = df.to_pandas_df(column_names=columns, selection=selection)

    # Read and add metadata in the DataFrame
    metadata = manager.read_metadata(fname)

    # Sanity Checks if loading the full file
    if not selection:
        if "total_lines" in metadata:
            assert len(df) == metadata["total_lines"]
        if "wavenumber_min" in metadata:
            assert df["wav"].min() == metadata["wavenumber_min"]
        if "wavenumber_max" in metadata:
            assert df["wav"].max() == metadata["wavenumber_max"]

    if isinstance(metadata, list):
        metadata_dict = {}
        for k, v in metadata[0].items():
            metadata_dict[k] = [v] + [M[k] for M in metadata[1:]]
        metadata = metadata_dict
    df.attrs.update(metadata)

    if verbose >= 3:
        from radis.misc.printer import printg

        printg(
            f"Generated dataframe from {fname} in {time()-t0:.2f}s ({len(df)} rows, {len(df.columns)} columns, {sys.getsizeof(df)*1e-6:.2f} MB)"
        )

    return df


#%%

if __name__ == "__main__":

    import pytest

    print("Testing factory:", pytest.main(["../test/io/test_hdf5.py"]))
