#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This file is part of pyunicorn.
# Copyright (C) 2008--2015 Jonathan F. Donges and pyunicorn authors
# URL: <http://www.pik-potsdam.de/members/donges/software>
# License: BSD (3-clause)

"""
Provides classes for analyzing spatially embedded complex networks, handling
multivariate data.
Written by Jakob Runge.
"""

import numpy                        # array object and fast numerics
from scipy import weave             # C++ inline code
from scipy import special, linalg           # special math functions

# import mpi                  # parallelized computations


#
#  Define class Coupling Analysis
#

class CouplingAnalysis(object):

    """
    Contains methods to calculate coupling matrices from large arrays
    of scalar time series.
    Comprises linear and information-theoretic measures, lagged
    and directed couplings.
    """

    #
    #  Definitions of internal methods
    #

    def __init__(self, data, silence_level=0):
        """
        Initialize an instance of CouplingAnalysis from data array.

        :type data: multidimensional numpy array
        :arg data: The time series array with time in first dimension.
        :type silence_level: int >= 0
        :arg  silence_level: The higher, the less progress info is output.
        """

        self.silence_level = silence_level
        """(int>=0) higher -> less progress info"""

        #  Flatten array along spatial dimensions to allow
        #  for more convinient indexing
        self.n_time = data.shape[0]
        self.data = data.reshape(self.n_time, -1)
        self.N = self.data.shape[1]

    def __str__(self):
        """Return a string representation of the CouplingAnalysis object."""
        text = CouplingAnalysis.__str__(self)

        return text

    @staticmethod
    def test_data():

        """Return example test data as discussed in pyunicorn description paper."""

        numpy.random.seed(42)
        noise = numpy.random.randn(1000,4)
        data = noise
        for t in xrange(2,1000):
            data[t,0] = 0.8* data[t-1,0] + noise[t,0]
            data[t,1] = 0.8* data[t-1,1] + 0.5* data[t-2,0]+ noise[t,1]
            data[t,2] = 0.7* data[t-1,0] + noise[t,2]
            data[t,3] = 0.7* data[t-2,0] + noise[t,3]

        return data
        # return numpy.array(
        #   [[ 0.77660516, -2.01163192,  0.09600993, -1.11162767],
        #    [ 1.65889602, -0.22372264, -0.44640601,  0.69750562],
        #    [ 0.01330197,  1.36374369, -0.54593782,  0.59673937],
        #    [ 2.32844604,  0.29933479,  0.04857109, -0.15667461],
        #    [-0.80080118, -1.11100112,  0.06016349, -1.12803442],
        #    [-1.16433538, -1.46249166, -0.0364203 ,  0.09615883],
        #    [ 1.68238403,  0.22191866, -0.13925702, -0.22751562],
        #    [-0.0086563 ,  1.72203867,  1.76003454,  0.26190748],
        #    [-0.57731838,  0.95973436,  1.48255192,  0.59388952],
        #    [ 0.21311645,  1.06136778,  0.89155714,  1.02664768]])

    def symmetrize_by_absmax(self, similarity_matrix, lag_matrix):

        """
        Returns symmetrized similarity matrix.

        Computes the largest absolute value for each pair (i,j) and (j,i) and
        returns the in-place changed matrices of measures and lags. A negative
        lag for an entry (i,j) in the lag_matrix then indicates a 'direction'
        j --> i regarding the peak of the lag function, and vice versa for a
        positive lag.

        **Example:**

        >>> coup_ana = CouplingAnalysis(CouplingAnalysis.test_data())
        >>> similarity_matrix, lag_matrix = coup_ana.cross_correlation(tau_max=2)
        >>> similarity_matrix, lag_matrix
        (array([[ 1.        , -0.4109135 , -0.25229099, -0.33319607],
               [-0.29882076,  1.        ,  0.52695286,  0.66663224],
               [-0.35580596,  0.48990893,  1.        ,  0.71206021],
               [ 0.55088627,  0.66663224,  0.36762539,  1.        ]],
               dtype=float32),
        array([[0, 2, 2, 1],
               [2, 0, 1, 0],
               [1, 0, 0, 2],
               [1, 0, 0, 0]], dtype=int8))
        >>> coup_ana.symmetrize_by_absmax(similarity_matrix, lag_matrix)
        (array([[ 1.        , -0.4109135 , -0.35580596,  0.55088627],
               [-0.4109135 ,  1.        ,  0.52695286,  0.66663224],
               [-0.35580596,  0.52695286,  1.        ,  0.71206021],
               [ 0.55088627,  0.66663224,  0.71206021,  1.        ]],
               dtype=float32),
        array([[ 0,  2, -1, -1],
               [-2,  0,  1,  0],
               [ 1, -1,  0,  2],
               [ 1,  0, -2,  0]], dtype=int8))

        :type similarity_matrix: array-like [float]
        :arg  similarity_matrix:  array-like [node, node] matrix of similarity estimates

        :type lag_matrix: array-like [int>=0]
        :arg  lag_matrix:  array-like [node, node] matrix of lags

        :rtype: tuple of arrays
        :returns: the value at the absolute maximum and the (pos or neg) lag.
        """

        N = self.N

        code = r"""
        int i,j;
        // loop over all node pairs
        for (i = 0; i < N; i++) {
            for (j = i+1; j < N; j++) {
                // calculate max and argmax by comparing to
                // previous value and storing max
                if (fabs(similarity_matrix(i,j)) > fabs(similarity_matrix(j,i))) {
                    similarity_matrix(j,i) = similarity_matrix(i,j);
                    lag_matrix(j,i) = -lag_matrix(i,j);
                }
                else {
                    similarity_matrix(i,j) = similarity_matrix(j,i);
                    lag_matrix(i,j) = -lag_matrix(j,i);
                }
            }
        }
        """
        args = ['similarity_matrix', 'lag_matrix', 'N']
        weave.inline(code, arg_names=args,
                     type_converters=weave.converters.blitz, compiler='gcc',
                     extra_compile_args=["-O3"])

        return similarity_matrix, lag_matrix

    #
    #  Define methods to estimate similarity measures
    #
    def cross_correlation(self, tau_max=0, lag_mode='max'):

        """Return cross correlation between all pairs of nodes.

        Two lag-modes are available (default: lag_mode='max'):

        lag_mode = 'all':
        Return 3-dimensional array of lagged cross correlations between all
        pairs of nodes. An entry (i, j, tau) corresponds to
        rho(X^i_t-tau, X^j_t) for positive lags tau, i.e., the direction
        i --> j for tau != 0.

        lag_mode = 'max':
        Return matrix of absolute maxima and corresponding lags of lagged
        cross correlation (CC) between all pairs of nodes.
        Returns two usually asymmetric matrices of CC values and lags:
        In each matrix, an entry (i, j) corresponds to the (positive or
        negative) value and lag, respectively, at absolute maximum of
        rho(X^i_t-tau, X^j_t) for positive lags tau, i.e., the direction i --> j
        for tau > 0. The matrices are, thus, asymmetric. The function
        coup_ana.symmetrize_by_absmax(...) can be used to obtain a symmetric
        matrix.

        **Example:**

        >>> coup_ana = CouplingAnalysis(CouplingAnalysis.test_data())
        >>> similarity_matrix, lag_matrix = coup_ana.cross_correlation(
                                            tau_max=5, lag_mode='max')
        >>> similarity_matrix, lag_matrix
        (array([[ 1.        ,  0.75700164,  0.77901524,  0.753622  ],
               [ 0.48466146,  1.        ,  0.45020837,  0.51969653],
               [ 0.62185854,  0.58438593,  1.        ,  0.59916633],
               [ 0.48268536,  0.55088729,  0.49959469,  1.        ]],
               dtype=float32),
        array([[0, 4, 1, 2],
               [0, 0, 0, 0],
               [0, 3, 0, 1],
               [0, 2, 0, 0]], dtype=int8))

        :type tau_max: int [int>=0]
        :arg  tau_max: maximum lag of cross correlation lag function.

        :type lag_mode: str [('max'|'all')]
        :arg  lag_mode: lag-mode of cross correlations to return.

        :rtype: 3D-array or tuple of matrices
        :returns: all-lag array or matrices of value and lag at the absolute
                  maximum.
        """

        data = self.data
        T, N = data.shape

        # Sanity checks
        if type(data) != numpy.ndarray:
            raise TypeError("data is of type %s, " % type(data) +
                            "must be numpy.ndarray")
        if N > T:
            print("Warning: data.shape = %s," % str(data.shape) +
                          " is it of shape (observations, variables) ?")
        if numpy.isnan(data).sum() != 0:
            raise ValueError("NaNs in the data")
        if tau_max < 0:
            raise ValueError("tau_max = %d, " % (tau_max)
                             + "but 0 <= tau_max")
        if lag_mode not in ['max', 'all']:
            raise ValueError("lag_mode = %s, " % (lag_mode)
                             + "but must be one of 'max', 'all'")

        #  Normalize time series to zero mean and unit variance for all lags
        corr_range = T - tau_max
        array = numpy.empty((tau_max + 1, N, corr_range), dtype="float32")

        for t in range(tau_max + 1):
            #  Remove mean value from time series at each node
            array[t] = numpy.fastCopyAndTranspose(data[t:t+corr_range,:] - \
                         data[t:t+corr_range,:].mean(axis=0).reshape(1, N))

            #  Normalize the variance of anomalies to one
            array[t] /= array[t].std(axis=1).reshape(N, 1)

            #  Correct for nodes with zero variance in their time series
            array[t][numpy.isnan(array[t])] = 0

        if lag_mode == 'max':
            similarity_matrix = numpy.ones((self.N, self.N), dtype='float32')
            lag_matrix = numpy.zeros((self.N, self.N), dtype='int8')

            code = r"""
            int i,j,tau,k, argmax;
            double crossij, max;
            // loop over all node pairs, NOT symmetric due to time shifts!
            for (i = 0; i < N; i++) {
                for (j = 0; j < N; j++) {
                    if( i != j){
                        max = 0.0;
                        argmax = 0;
                        // loop over taus INCLUDING the last tau value
                        for( tau = 0; tau < tau_max + 1; tau++) {
                            crossij = 0;
                            // here the actual cross correlation is calculated
                            // assuming standardized arrays
                            for ( k = 0; k < corr_range; k++) {
                                crossij += array(tau, i, k) * array(tau_max, j, k);
                            }
                            // calculate max and argmax by comparing to
                            // previous value and storing max
                            if (fabs(crossij) > fabs(max)) {
                                max = crossij;
                                argmax = tau;
                            }
                        }
                        similarity_matrix(i,j) = max/(float)(corr_range);
                        lag_matrix(i,j) = tau_max - argmax;
                    }
                }
            }
            """

            args = ['array', 'similarity_matrix', 'lag_matrix', 'N', 'tau_max',
                    'corr_range']

            weave.inline(code, arg_names=args,
                         type_converters=weave.converters.blitz, compiler='gcc',
                         extra_compile_args=["-O3"])

            return similarity_matrix, lag_matrix

        elif lag_mode == 'all':

            lagfuncs = numpy.zeros((self.N, self.N, tau_max+1),
                                    dtype='float32')

            code = r"""
            int i,j,tau,k, argmax;
            double crossij, max;
            // loop over all node pairs, NOT symmetric due to time shifts!
            for (i = 0; i < N; i++) {
                for (j = 0; j < N; j++) {
                    // loop over taus INCLUDING the last tau value
                    for( tau = 0; tau < tau_max + 1; tau++) {
                        crossij = 0;
                        // here the actual cross correlation is calculated
                        // assuming standardized arrays
                        for ( k = 0; k < corr_range; k++) {
                            crossij += array(tau, i, k) * array(tau_max, j, k);
                        }
                        lagfuncs(i,j,tau_max-tau) = crossij/(float)(corr_range);
                    }
                }
            }
            """

            args = ['array', 'lagfuncs', 'N', 'tau_max',
                    'corr_range']

            weave.inline(code, arg_names=args,
                         type_converters=weave.converters.blitz, compiler='gcc',
                         extra_compile_args=["-O3"])

            return lagfuncs

    def mutual_information(self, tau_max=0, estimator='knn',
                           knn=10, bins=6, lag_mode='max'):

        """
        Return mutual information (MI) between all pairs of nodes.

        Three estimators are available:

        estimator = 'knn' (Recommended):
        Based on k-nearest-neighbors [Kraskov2004]_,
        version 1 in their paper. Larger k have smaller variance, but larger
        (typically negative) bias, and vice versa.

        estimator = 'binning':
        Binning estimator based on equal-quantile binning.

        estimator = 'gauss':
        Captures only linear part of association. Essentially estimates a
        transformed partial correlation.


        Two lag-modes are available (default: lag_mode='max'):

        lag_mode = 'all':
        Return 3-dimensional array of lagged MI between all
        pairs of nodes. An entry (i, j, tau) corresponds to
        I(X^i_t-tau, X^j_t) for positive lags tau, i.e., the direction
        i --> j for tau != 0.

        lag_mode = 'max':
        Return matrix of absolute maxima and corresponding lags of lagged
        MI between all pairs of nodes.
        Returns two usually asymmetric matrices of MI values and lags:
        In each matrix, an entry (i, j) corresponds to the value and lag,
        respectively, at absolute maximum of I(X^i_t-tau, X^j_t) for
        positive lags tau, i.e., the direction i --> j for tau > 0.
        The matrices are, thus, asymmetric. The function
        coup_ana.symmetrize_by_absmax(...) can be used to obtain a symmetric
        matrix.

        Reference: [Kraskov2004]_

        **Example:**

        >>> coup_ana = CouplingAnalysis(CouplingAnalysis.test_data())
        >>> similarity_matrix, lag_matrix = coup_ana.mutual_information(
                                            tau_max=5, knn=10, estimator='knn')
        >>> similarity_matrix, lag_matrix
        (array([[ 4.65048742,  0.43874303,  0.46520019,  0.41257444],
               [ 0.14704162,  4.65048742,  0.10645443,  0.16393046],
               [ 0.24829103,  0.2125767 ,  4.65048742,  0.22044939],
               [ 0.12093173,  0.19902836,  0.14530452,  4.65048742]],
               dtype=float32),
        array([[0, 4, 1, 2],
               [0, 0, 0, 0],
               [0, 2, 0, 1],
               [0, 2, 0, 0]], dtype=int8))

        :type tau_max: int [int>=0]
        :arg  tau_max: maximum lag of MI lag function.

        :type knn: int [int>=1]
        :arg  knn: nearest-neighbor MI estimation parameter. (default: 10)

        :type bins: int [int>=2]
        :arg  bins: binning MI estimation parameter. (default: 6)

        :type estimator: str [('knn'|'binning'|'gauss')]
        :arg  estimator: MI estimator. (default: 'knn')

        :type lag_mode: str [('max'|'all')]
        :arg  lag_mode: lag-mode of MI to return.

        :rtype: 3D-array or tuple of matrices
        :returns: all-lag array or matrices of value and lag at the absolute
                  maximum.
        """

        data = self.data
        T, N = data.shape

        # Sanity checks
        if type(data) != numpy.ndarray:
            raise TypeError("data is of type %s, " % type(data) +
                            "must be numpy.ndarray")
        if N > T:
            print("Warning: data.shape = %s," % str(data.shape) +
                          " is it of shape (observations, variables) ?")
        if T < 500:
            print("Warning: T = %s ," % str(T) +
                          " unreliable estimation using MI estimator")
        if numpy.isnan(data).sum() != 0:
            raise ValueError("NaNs in the data")
        if tau_max < 0:
            raise ValueError("tau_max = %d, " % (tau_max)
                             + "but 0 <= tau_max")
        if estimator == 'knn':
            if (knn > T/2. or knn < 1):
                raise ValueError("knn = %s , " % str(knn) +
                                 "should be between 1 and T/2")

        if lag_mode == 'max':
            similarity_matrix = numpy.ones((N, N), dtype='float32')
            lag_matrix = numpy.zeros((N, N), dtype='int8')
        elif lag_mode == 'all':
            lagfuncs = numpy.zeros((N, N, tau_max+1),
                                    dtype='float32')

        if estimator == 'binning':
            self.plogp = self.create_plogp(T)

        for i in range(N):
            for j in range(N):
                maximum = 0.
                lag_at_max = 0
                for tau in range(tau_max + 1):

                    X = [(i, -tau)]
                    Y = [(j, 0)]
                    Z = []

                    XYZ = X + Y + Z
                    dim = len(XYZ)
                    max_lag = tau_max
                    array = numpy.zeros((dim, T - max_lag))
                    for d, node in enumerate(XYZ):
                        var, lag = node
                        array[d, :] = data[max_lag + lag: T + lag, var]

                    if estimator == 'knn':
                        xyz = numpy.array([0, 1])

                        k_xz, k_yz, k_z = self._get_nearest_neighbors(
                                            array=array, xyz=xyz,
                                             k=knn, standardize=True)

                        ixy_z = (special.digamma(knn)
                                 + (- special.digamma(k_xz)
                                    - special.digamma(k_yz)
                                    + special.digamma(k_z)).mean())

                    elif estimator == 'binning':
                        symb_array = self._quantile_bin_array(array, bins=bins)

                        ## High-dimensional Histogram
                        hist = self.bincount_hist(symb_array)

                        ## Entropies by use of vectorized function plogp
                        hxyz = (-(self.plogp(hist)).sum()
                                + self.plogp(T))/float(T)
                        hxz = (-(self.plogp(hist.sum(axis=1))).sum()
                               + self.plogp(T))/float(T)
                        hyz = (-(self.plogp(hist.sum(axis=0))).sum()
                               + self.plogp(T))/float(T)
                        hz = (-(self.plogp(hist.sum(axis=0).sum(axis=0))).sum()
                              + self.plogp(T))/float(T)

                        ixy_z = hxz + hyz - hz - hxyz

                    elif estimator == 'gauss':

                        # Standardize
                        array -= array.mean(axis=1).reshape(dim, 1)
                        array /= array.std(axis=1).reshape(dim, 1)
                        if numpy.isnan(array).sum() != 0:
                            raise ValueError("nans after standardizing, "
                                             "possibly constant array!""")

                        x = array[0, :]
                        y = array[1, :]

                        ixy_z = self._par_corr_to_cmi(numpy.dot(x, y)
                                / numpy.sqrt(numpy.dot(x, x) * numpy.dot(y, y)))

                    if lag_mode == 'max':
                        if ixy_z > maximum:
                            maximum = ixy_z
                            lag_at_max = tau

                    elif lag_mode == 'all':
                        lagfuncs[i,j,tau] = ixy_z

                if lag_mode == 'max':
                    similarity_matrix[i,j] = maximum
                    lag_matrix[i,j] = lag_at_max

        if lag_mode == 'max':
            return similarity_matrix, lag_matrix
        elif lag_mode == 'all':
            return lagfuncs

    def information_transfer(self, tau_max=0, estimator='knn',
                           knn=10, past=1, cond_mode='ity', lag_mode='max'):

        """
        Return bivariate information transfer between all pairs of nodes.

        Two condition modes of information transfer are available
        as described in [Runge2012b]_.

        Information transfer to Y (ITY):
        I(X^i_t-tau, X^j_t | X^j_t-1, ...,X^j_t-past)

        Momentary information transfer (MIT):
        I(X^i_t-tau, X^j_t | X^j_t-1, ...,X^j_t-past, X^i_t-tau-1,...
                                                           ...,X^j_t-tau-past)

        Two estimators are available:

        estimator = 'knn' (Recommended):
        Based on k-nearest-neighbors [Kraskov2004]_,
        version 1 in their paper. Larger k have smaller variance, but larger
        (typically negative) bias, and vice versa.

        estimator = 'gauss':
        Captures only linear part of association. Essentially estimates a
        transformed partial correlation.


        Two lag-modes are available (default: lag_mode='max'):

        lag_mode = 'all':
        Return 3-dimensional array of lag-functions between all
        pairs of nodes. An entry (i, j, tau) corresponds to
        I(X^i_t-tau, X^j_t | ...) for positive lags tau,
        i.e., the direction i --> j for tau != 0.

        lag_mode = 'max':
        Return matrix of absolute maxima and corresponding lags of lag-functions
        between all pairs of nodes.
        Returns two usually asymmetric matrices of values and lags:
        In each matrix, an entry (i, j) corresponds to the value and lag,
        respectively, at absolute maximum of
        I(X^i_t-tau, X^j_t | ...) for
        positive lags tau, i.e., the direction i --> j for tau > 0.
        The matrices are, thus, asymmetric. The function
        coup_ana.symmetrize_by_absmax(...) can be used to obtain a symmetric
        matrix.

        **Example:**

        >>> coup_ana = CouplingAnalysis(CouplingAnalysis.test_data())
        >>> similarity_matrix, lag_matrix = coup_ana.information_transfer(
                                            tau_max=5, estimator='knn', knn=10)
        >>> similarity_matrix, lag_matrix
        (array([[ 0.        ,  0.15439266,  0.32609266,  0.30471787],
               [ 0.02184407,  0.        ,  0.03941471,  0.09759291],
               [ 0.01338544,  0.06634707,  0.        ,  0.15019628],
               [ 0.00658225,  0.06942768,  0.04013694,  0.        ]],
               dtype=float32),
        array([[0, 2, 1, 2],
               [5, 0, 0, 0],
               [5, 1, 0, 1],
               [5, 0, 0, 0]], dtype=int8))

        :type tau_max: int [int>=0]
        :arg  tau_max: maximum lag of ITY lag function.

        :type past: int [int>=1]
        :arg  past: maximum lag of past history.

        :type knn: int [int>=1]
        :arg  knn: nearest-neighbor ITY estimation parameter. (default: 10)

        :type bins: int [int>=2]
        :arg  bins: binning ITY estimation parameter. (default: 6)

        :type estimator: str [('knn'|'gauss')]
        :arg  estimator: ITY estimator. (default: 'knn')

        :type cond_mode: str [('ity'|'mit')]
        :arg  cond_mode: condition mode. (default: 'ity')

        :type lag_mode: str [('max'|'all')]
        :arg  lag_mode: lag-mode of ITY to return.

        :rtype: 3D-array or tuple of matrices
        :returns: all-lag array or matrices of value and lag at the absolute
                  maximum.
        """

        data = self.data
        T, N = data.shape

        # Sanity checks
        if type(data) != numpy.ndarray:
            raise TypeError("data is of type %s, " % type(data) +
                            "must be numpy.ndarray")
        if N > T:
            print("Warning: data.shape = %s," % str(data.shape) +
                          " is it of shape (observations, variables) ?")
        if estimator == 'knn' and T < 500:
            print("Warning: T = %s ," % str(T) +
                          " unreliable estimation using knn-estimator")
        if numpy.isnan(data).sum() != 0:
            raise ValueError("NaNs in the data")
        if tau_max < 0:
            raise ValueError("tau_max = %d, " % (tau_max)
                             + "but 0 <= tau_max")
        if estimator == 'knn':
            if (knn > T/2. or knn < 1):
                raise ValueError("knn = %s , " % str(knn) +
                                 "should be between 1 and T/2")

        if lag_mode == 'max':
            similarity_matrix = numpy.ones((N, N), dtype='float32')
            lag_matrix = numpy.zeros((N, N), dtype='int8')
        elif lag_mode == 'all':
            lagfuncs = numpy.zeros((N, N, tau_max+1),
                                    dtype='float32')

        for i in range(N):
            for j in range(N):
                maximum = 0.
                lag_at_max = 0
                for tau in range(tau_max + 1):

                    X = [(i, -tau)]
                    Y = [(j, 0)]
                    if cond_mode == 'ity':
                        Z = [(j, -p) for p in range(1, past + 1)]
                    elif cond_mode == 'mit':
                        Z = [(j, -p) for p in range(1, past + 1)]
                        Z += [(i, -tau -p) for p in range(1, past + 1)]

                    XYZ = X + Y + Z

                    dim = len(XYZ)
                    max_lag = tau_max + past
                    array = numpy.zeros((dim, T - max_lag))
                    for d, node in enumerate(XYZ):
                        var, lag = node
                        array[d, :] = data[max_lag + lag: T + lag, var]

                    if estimator == 'knn':
                        xyz = numpy.array([0, 1])

                        k_xz, k_yz, k_z = self._get_nearest_neighbors(
                                            array=array, xyz=xyz,
                                             k=knn, standardize=True)

                        ixy_z = (special.digamma(knn)
                                 + (- special.digamma(k_xz)
                                    - special.digamma(k_yz)
                                    + special.digamma(k_z)).mean())

                    elif estimator == 'gauss':

                        if numpy.isnan(array).sum() != 0:
                            raise ValueError("nans in the array!")

                        # Standardize
                        array -= array.mean(axis=1).reshape(dim, 1)
                        array /= array.std(axis=1).reshape(dim, 1)
                        if numpy.isnan(array).sum() != 0:
                            raise ValueError("nans after standardizing, "
                                             "possibly constant array!""")

                        x = array[0, :]
                        y = array[1, :]
                        if len(array) > 2:
                            confounds = array[2:, :]
                            ortho_confounds = linalg.qr(
                                numpy.fastCopyAndTranspose(confounds),
                                mode='economic')[0].T
                            x -= numpy.dot(numpy.dot(ortho_confounds, x),
                                    ortho_confounds)
                            y -= numpy.dot(numpy.dot(ortho_confounds, y),
                                    ortho_confounds)

                        ixy_z = self._par_corr_to_cmi(numpy.dot(x, y)
                                / numpy.sqrt(numpy.dot(x, x) * numpy.dot(y, y)))

                    if lag_mode == 'max':
                        if ixy_z > maximum:
                            maximum = ixy_z
                            lag_at_max = tau

                    elif lag_mode == 'all':
                        lagfuncs[i,j,tau] = ixy_z

                if lag_mode == 'max':
                    similarity_matrix[i,j] = maximum
                    lag_matrix[i,j] = lag_at_max

        if lag_mode == 'max':
            similarity_matrix[range(N), range(N)] = 0.
        elif lag_mode == 'all':
            lagfuncs[range(N), range(N), 0.] = 0.

        if lag_mode == 'max':
            return similarity_matrix, lag_matrix
        elif lag_mode == 'all':
            return lagfuncs

    #
    #  Define helper methods
    #

    def _par_corr_to_cmi(self, par_corr):
        """
        Transformation of partial correlation to conditional mutual
        information scale using the (multivariate) Gaussian assumption.

        :type par_corr: float or array
        :arg  par_corr: partial correlation

        :rtype: float
        :returns: transformed partial correlation.
        """

        return -0.5*numpy.log(1. - par_corr**2)

    def _get_nearest_neighbors(self, array, xyz, k, standardize=True):

        """
        Returns nearest-neighbors for conditional mutual information estimator.

        Reference: [Kraskov2004]_

        :type array: array (float)
        :arg  array: data array.

        :type xyz: array [int(0|1|2)]
        :arg  xyz: identifier of X, Y, Z in CMI

        :type k: int [int>=1]
        :arg  k: nearest-neighbor MI estimation parameter.

        :type standardize: bool
        :arg  standardize: standardize array before estimation. (default: True)

        :rtype: tuple of arrays
        :returns: nearest neighbors for each sample point.
        """

        dim, T = array.shape

        if standardize:
            # Standardize
            array = array.astype('float32')
            array -= array.mean(axis=1).reshape(dim, 1)
            array /= array.std(axis=1).reshape(dim, 1)
            # If the time series is constant, return nan rather than raising
            # Exception
            if numpy.isnan(array).sum() != 0:
                raise ValueError("nans after standardizing, "
                                 "possibly constant array!")

        # Add noise to destroy ties...
        array += 1E-10 * numpy.random.rand(array.shape[0], array.shape[1])

        # Flatten for fast weave.inline access
        array = array.flatten()

        dim_x = int(numpy.where(xyz == 0)[0][-1] + 1)
        dim_y = int(numpy.where(xyz == 1)[0][-1] + 1 - dim_x)
        # dim_z = maxdim - dim_x - dim_y

        # Initialize
        k_xz = numpy.zeros(T, dtype='int32')
        k_yz = numpy.zeros(T, dtype='int32')
        k_z = numpy.zeros(T, dtype='int32')

        code = """
        int i, j, index=0, t, m, n, d, kxz, kyz, kz, indexfound[T];//
        double  dz=0., dxyz=0., dx=0., dy=0., eps, epsmax;
        double dist[T*dim], dxyzarray[k+1];

        // Loop over time
        for(i = 0; i < T; i++){

            // Growing cube algorithm: Test if n = #(points in epsilon-
            // environment of reference point i) > k
            // Start with epsilon for which 95% of points are inside the cube
            // for a multivariate Gaussian
            // eps increased by 2 later, also the initial eps
            eps = 1.*pow( float(k)/float(T), 1./dim);

            // n counts the number of neighbors
            n = 0;
            while(n <= k){
                // Increase cube size
                eps *= 2.;
                // Start with zero again
                n = 0;
                // Loop through all points
                for(t = 0; t < T; t++){
                    d = 0;
                    while(fabs(array[d*T + i] - array[d*T + t] ) < eps
                            && d < dim){
                            d += 1;
                    }
                    // If all distances are within eps, the point t lies
                    // within eps and n is incremented
                    if(d == dim){
                        indexfound[n] = t;
                        n += 1;
                    }
                }
            }

            // Calculate distance to points only within epsilon environment
            // according to maximum metric
            for(j = 0; j < n; j++){
                index = indexfound[j];

                dxyz = 0.;
                for(d = 0; d < dim; d++){
                    dist[d*T + j] = fabs(array[d*T + i] - array[d*T + index]);
                    dxyz = fmax( dist[d*T + j], dxyz);
                }

                // Use insertion sort
                dxyzarray[j] = dxyz;
                if ( j > 0 ){
                    // only list of smallest k+1 distances need to be kept!
                    m = fmin(k, j-1);
                    while ( m >= 0 && dxyzarray[m] > dxyz ){
                        dxyzarray[m+1] = dxyzarray[m];
                        m -= 1;
                    }
                    dxyzarray[m+1] = dxyz;
                }

            }

            // Epsilon of k-th nearest neighbor in joint space
            epsmax = dxyzarray[k];

            // Count neighbors within epsmax in subspaces, since the reference
            // point is included, all neighbors are at least 1
            kz = 0;
            kxz = 0;
            kyz = 0;
            for(j = 0; j < T; j++){

                // X-subspace
                dx = fabs(array[0*T + i] - array[0*T + j]);
                for(d = 1; d < dim_x; d++){
                    dist[d*T + j] = fabs(array[d*T + i] - array[d*T + j]);
                    dx = fmax( dist[d*T + j], dx);
                }

                // Y-subspace
                dy = fabs(array[dim_x*T + i] - array[dim_x*T + j]);
                for(d = dim_x; d < dim_x+dim_y; d++){
                    dist[d*T + j] = fabs(array[d*T + i] - array[d*T + j]);
                    dy = fmax( dist[d*T + j], dy);
                }

                // Z-subspace, if empty, dz stays 0
                dz = 0.;
                for(d = dim_x+dim_y; d < dim ; d++){
                    dist[d*T + j] = fabs(array[d*T + i] - array[d*T + j]);
                    dz = fmax( dist[d*T + j], dz);
                }

                // For no conditions, kz is counted up to T
                if (dz < epsmax){
                    kz += 1;
                    if (dx < epsmax){
                        kxz += 1;
                    }
                    if (dy < epsmax){
                        kyz += 1;
                    }
                }
            }
            // Write to numpy arrays
            k_xz[i] = kxz;
            k_yz[i] = kyz;
            k_z[i] = kz;

        }
        """

        vars = ['array', 'T', 'dim_x', 'dim_y',
                'k', 'dim', 'k_xz', 'k_yz', 'k_z']

        weave.inline(
            code, vars, headers=["<math.h>"], extra_compile_args=['-O3'])

        return k_xz, k_yz, k_z

    def _quantile_bin_array(self, array, bins=6):

        """
        Returns symbolified array with aequi-quantile binning.

        This partition results in a uniform distribution of the marginals.

        :type array: array
        :arg array: data

        :type bins: int
        :arg bins: number of bins

        :rtype: array
        :returns: converted data
        """

        dim, T = array.shape

        ## get the bin quantile steps
        bin_edge = numpy.ceil(T/float(bins))

        symb_array = numpy.zeros( (dim, T), dtype = 'int32')

        ## get the lower edges of the bins for every time series
        edges = numpy.sort(array, axis=1)[:, ::bin_edge]
        bins = edges.shape[1]

        ## This gives the symbolic time series
        symb_array =  ( array.reshape(dim,T,1) >=
                        edges.reshape(dim,1,bins) ).sum(axis=2) - 1

        return symb_array


    def bincount_hist(self, symb_array):

        """
        Computes histogram from symbolic array.

        :type symb_array: array of integers
        :arg symb_array: symbolic data

        :rtype: array
        :returns: (unnormalized) histogram
        """

        base = int(symb_array.max() + 1)

        D, T = symb_array.shape

        assert type(base**D) == int     ## Needed because numpy.bincount cannot process longs
        assert base**D*16./8./1024.**3 < 3., 'Dimension exceeds 3 GB of necessary memory (change this code line if you got more...)'
        assert D*base**D < 2**65, 'base = %d, D = %d: Histogram failed: dimension D*base**D exceeds int64 data type' %(base, D)

        flathist = numpy.zeros((base**D), dtype='int16')
        multisymb = numpy.zeros(T, dtype='int64')

        for i in xrange(D):
            multisymb += symb_array[i,:]*base**i


        result = numpy.bincount(multisymb)
        flathist[:len(result)] += result

        return flathist.reshape(tuple([base,base] + [base for i in range(D-2)]) ).T

    def create_plogp(self, T):

        """
        Precalculation of p*log(p) needed for entropies.

        :type T: int
        :arg  T: sample length

        :rtype: array
        :returns: p*log(p) array from p=1 to p=T
        """

        gfunc = numpy.zeros(T+1)
        gfunc[1:] = numpy.arange(1, T+1, 1)*numpy.log(numpy.arange(1, T+1, 1))

        def plogp_func(t):
            return gfunc[t]

        return numpy.vectorize(plogp_func)
