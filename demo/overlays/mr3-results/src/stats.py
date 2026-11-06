import os
import numpy as np


def mean_error(curves):
    return np.mean([c[-1] for c in curves])
