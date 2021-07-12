# -*- coding: utf-8 -*-
"""
Created on Mon Jul 12 09:13:51 2021

@author: mines
"""

from numba import jit
from numpy import exp, abs
from radis.phys.constants import hc_k  # ~ 1.44 cm.K


@jit(nopython=True)
def partial_partition_sum_nargs(
    gvib_arr,
    Evib_arr,
    grot_arr,
    Erot_arr,
    Trot,
    Tvib,
    vib_distribution,
    rot_distribution,
    N=1000,
    rtol=1e-15,
):
    """
    Partial sum of the partition function is incremented until convergence. See also: https://github.com/radis/radis-benchmark/blob/master/manual_benchmarks/fast-parsum.ipynb.
    Parameters must be separated so that @jit can recognize types.
    
    Parameters
    ----------
    gvib_arr : Array of float.
        Degeneracy of vibration.
    Evib_arr : Array of float.
        Energy of vibration.
    grot_arr : Array of float.
        Degeneracy of rotation.
    Erot_arr : Array of float.
        Energy of rotation.
    Trot : Float.
        Rotational temperature.
    Tvib : Float.
        Vibrational temperature.
    vib_distribution: ``'boltzmann'``, ``'treanor'``
        Distribution of vibrational levels
    rot_distribution: ``'boltzmann'``
        Distribution of rotational levels
    N : Float., optional
        Number of states to add per increment. The default is 100000.
    rtol : Float., optional
        Relative tolerance for convergence. The default is 0.003e-2.

    Returns
    -------
    s : Float.
        Partition function summed until convergence.

    """
    slast = 0
    if vib_distribution == "boltzmann":
        vib = gvib_arr[:N] * exp(-hc_k * Evib_arr[:N] / Tvib)
    elif vib_distribution == "treanor":
        vib = gvib_arr[:N] * exp(-hc_k * (Evib_arr[:N] / Tvib + Evib_arr[:N] / Trot))
    else:
        raise NotImplementedError

    if rot_distribution == "boltzmann":
        rot = grot_arr[:N] * exp(-hc_k * Erot_arr[:N] / Trot)
    else:
        raise NotImplementedError

    s = (rot * vib).sum()
    i = N
    while abs(slast - s) / s > rtol and i <= len(gvib_arr):
        slast = s
        vib_new = gvib_arr[i : i + N] * exp(-hc_k * Evib_arr[i : i + N] / Tvib)
        rot_new = grot_arr[i : i + N] * exp(-hc_k * Erot_arr[i : i + N] / Trot)
        s += (vib_new * rot_new).sum()
        i += N

    return s