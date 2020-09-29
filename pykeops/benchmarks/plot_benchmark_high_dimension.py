"""
Benchmarking Gaussian convolutions in high dimensions
===========================================================

Let's compare the performances of PyTorch and KeOps on 
simple Gaussian RBF kernel products,
as the dimension grows.
 
"""


##############################################
# Setup
# ---------------------

import importlib
import os
import time

import numpy as np
import torch
from matplotlib import pyplot as plt

use_cuda = torch.cuda.is_available()

##############################################
# Benchmark specifications:
# 

N = 10000       # number of samples
MAXTIME = 10 if use_cuda else 10   # Max number of seconds before we break the loop
REDTIME = 2  if use_cuda else 2  # Decrease the number of runs if computations take longer than 2s...

# Dimensions to test
DS = [1, 3, 5, 10, ]
#      20, 30, 50, 
#      75, 100, 150, 
#      200, 300, 500,
#      1000, 2000, 3000]

##############################################
# Synthetic dataset. 

def generate_samples(D, device, lang, batchsize=None):
    """Create point clouds sampled from uniform distribution."""

    B = () if batchsize is None else (batchsize,)

    if lang == 'torch':
        if device == 'cuda':
            torch.cuda.manual_seed_all(1234)
        else:
            torch.manual_seed(1234)

        x = torch.rand(B + (N, D), device=device)

        y = torch.rand(B + (N, D), device=device)

        # Draw a random source signal:
        b = torch.randn(B + (N, 1), device=device)

    else:
        np.random.seed(1234)

        x = np.random.rand(*(B + (N, D))).astype('float32')
        y = np.random.rand(*(B + (N, D))).astype('float32')
        b = np.random.randn(*(B + (N,))).astype('float32')

    return x, y, b


##############################################
# Define a simple Gaussian RBF product, using a **tensorized** implementation:
#

def gaussianconv_numpy(x, y, b):
    K_xy = np.exp( - np.sum( (x[:,None,:] - y[None,:,:]) **2, axis=2) )
    
    return K_xy@b


def gaussianconv_pytorch(x, y, b):
    D_xx = (x*x).sum(-1).unsqueeze(1)         # (N,1)
    D_xy = torch.matmul( x, y.permute(1,0) )  # (N,D) @ (D,M) = (N,M)
    D_yy = (y*y).sum(-1).unsqueeze(0)         # (1,M)
    D_xy = D_xx - 2*D_xy + D_yy
    K_xy = (-D_xy).exp()

    return K_xy @ b

##############################################
# Define a simple Gaussian RBF product, using an **online** implementation:
#

from pykeops.torch import generic_sum

def gaussianconv_keops(x, y, b):
    D  = x.shape[1]
    fun = generic_sum("Exp(-SqDist(X,Y)) * B",  # Formula
                                 "A = Vi(1)",              # Output
                                 "X = Vi({})".format(D),   # 1st argument
                                 "Y = Vj({})".format(D),   # 2nd argument
                                 "B = Vj(1)" )             # 3rd argument
    backend = 'GPU' if use_cuda else 'CPU'
    return fun(x, y, b, backend=backend)

##############################################
# Same, but deactivating chunked computation scheme
#

from pykeops.torch import generic_sum

def gaussianconv_keops_nochunks(x, y, b):
    D  = x.shape[1]
    fun = generic_sum("Exp(-SqDist(X,Y)) * B",  # Formula
                                 "A = Vi(1)",              # Output
                                 "X = Vi({})".format(D),   # 1st argument
                                 "Y = Vj({})".format(D),   # 2nd argument
                                 "B = Vj(1)" )             # 3rd argument
    backend = 'GPU' if use_cuda else 'CPU'
    return fun(x, y, b, backend=backend, enable_chunks=False)

#############################################
# Finally, perform the same operation with our high-level :class:`pykeops.torch.LazyTensor` wrapper:

from pykeops.torch import LazyTensor


def gaussianconv_lazytensor(x, y, b):
    backend = 'GPU' if use_cuda else 'CPU'
    nbatchdims = len(x.shape) - 2
    x_i = LazyTensor(x.unsqueeze(-2))  # (B, M, 1, D)
    y_j = LazyTensor(y.unsqueeze(-3))  # (B, 1, N, D)
    D_ij = ((x_i - y_j) ** 2).sum(-1)  # (B, M, N, 1)
    K_ij = (- D_ij).exp()  # (B, M, N, 1)
    S_ij = K_ij * b.unsqueeze(-3)  # (B, M, N, 1) * (B, 1, N, 1)
    return S_ij.sum(dim=nbatchdims + 1, backend=backend)

##############################################
# Benchmarking loops
# -----------------------

def benchmark(routine_batchsize, dev, D, loops=10, lang='torch'):
    """Times a convolution on an N-by-N problem in dimension D."""

    if isinstance(routine_batchsize, tuple):
        Routine, B = routine_batchsize
    else:
        Routine, B = routine_batchsize, None

    importlib.reload(torch)  # In case we had a memory overflow just before...
    device = torch.device(dev)
    print(Routine)
    x, y, b = generate_samples(D, device, lang, batchsize=B)

    # We simply benchmark a convolution
    code = "a = Routine( x, y, b ) "
    exec( code, locals() ) # Warmup run, to compile and load everything

    t_0 = time.perf_counter()  # Actual benchmark --------------------
    if use_cuda: torch.cuda.synchronize()
    for i in range(loops):
        exec( code, locals() )
    if use_cuda: torch.cuda.synchronize()
    elapsed = time.perf_counter() - t_0  # ---------------------------

    if B is None:
        print("{:3} NxN convolution in dimension D, with N ={:7}, D={:7}: {:3}x{:3.6f}s".format(loops, N, D, loops, elapsed / loops))
        return elapsed / loops
    else:
        print("{:3}x{:3} NxN convolution in dimension D, with N ={:7}, D={:7}: {:3}x{:3}x{:3.6f}s".format(
            B, loops, N, D, B, loops, elapsed / (B * loops)))
        return elapsed / (B * loops)


def bench_config(Routine, backend, dev, l) :
    """Times a convolution for an increasing dimension."""

    print("Backend : {}, Device : {} -------------".format(backend, dev))

    times = []
    try :
        Nloops = [100, 10, 1]
        nloops = Nloops.pop(0)
        for d in DS :
            elapsed = benchmark(Routine, dev, d, loops=nloops, lang=l)

            times.append( elapsed )
            if (nloops * elapsed > MAXTIME) \
            or (nloops * elapsed > REDTIME/10 and len(Nloops) > 0 ) : 
                nloops = Nloops.pop(0)

    except RuntimeError :
        print("**\nMemory overflow !")
    except IndexError :
        print("**\nToo slow !")
    
    return times + (len(DS)-len(times)) * [np.nan]


def full_bench(title, routines) :
    """Benchmarks the varied backends of a geometric loss function."""

    backends = [ backend for (_, backend, _) in routines ]

    print("Benchmarking : {} ===============================".format(title))
    
    lines  = [ DS ]
    for routine, backend, lang in routines :
        lines.append( bench_config(routine, backend, "cuda" if use_cuda else "cpu", lang) )

    benches = np.array(lines).T

    # Creates a pyplot figure:
    plt.figure(figsize=(12,8))
    linestyles = ["o-", "s-", "^-"]
    for i, backend in enumerate(backends):
        plt.plot( benches[:,0], benches[:,i+1], linestyles[i], 
                  linewidth=2, label='backend = "{}"'.format(backend) )
        
        for (j, val) in enumerate( benches[:,i+1] ):
            if np.isnan(val) and j > 0:
                x, y = benches[j-1,0], benches[j-1,i+1]
                plt.annotate('Memory overflow!',
                    xy=(x, 1.05*y),
                    horizontalalignment='center',
                    verticalalignment='bottom')
                break

    plt.title('Runtimes for {} with N={}'.format(title, N))
    plt.xlabel('Dimension')
    plt.ylabel('Seconds')
    plt.yscale('log') ; plt.xscale('log')
    plt.legend(loc='upper left')
    plt.grid(True, which="major", linestyle="-")
    plt.grid(True, which="minor", linestyle="dotted")
    plt.axis([DS[0], DS[-1], 1e-5, MAXTIME])
    plt.tight_layout()

    # Save as a .csv to put a nice Tikz figure in the papers:
    header = "Dimension " + " ".join(backends)
    os.makedirs("output", exist_ok=True)
    np.savetxt("output/benchmark_convolutions_3D.csv", benches, 
               fmt='%-9.5f', header=header, comments='')


##############################################
# NumPy vs. PyTorch vs. KeOps (Gpu)
# --------------------------------------------------------

if use_cuda:
    routines = [ (gaussianconv_numpy,   "Numpy (Cpu)",   "numpy"),
                 (gaussianconv_pytorch, "PyTorch (Gpu)", "torch"),
                 (gaussianconv_keops,   "KeOps (Gpu)",   "torch"),
                 (gaussianconv_keops_nochunks,   "KeOps (non chunked mode, Gpu)",   "torch"), ]
    full_bench( "Gaussian Matrix-Vector products", routines )


##############################################
# NumPy vs. PyTorch vs. KeOps (Cpu)
# --------------------------------------------------------

use_cuda = False
routines = [ (gaussianconv_numpy,   "Numpy (Cpu)",   "numpy"),
             (gaussianconv_pytorch, "PyTorch (Cpu)", "torch"),
             (gaussianconv_keops,   "KeOps (Cpu)",   "torch"), ]
full_bench( "Gaussian Matrix-Vector products", routines )


################################################
# Genred vs. LazyTensor vs. batched LazyTensor
# ------------------------------------------------

use_cuda = torch.cuda.is_available()
routines = [(gaussianconv_keops, "KeOps (Genred)", "torch"),
            (gaussianconv_lazytensor, "KeOps (LazyTensor)", "torch"),
            ((gaussianconv_lazytensor, 10), "KeOps (LazyTensor, batchsize=10)", "torch"), ]
full_bench( "Gaussian Matrix-Vector products", routines )

plt.show()
