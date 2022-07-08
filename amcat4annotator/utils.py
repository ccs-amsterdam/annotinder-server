import random

def random_indices(seed: int, n: int) -> list:
    indices = [i for i in range(0, n)]
    random.seed(seed)
    random.shuffle(indices)
    return indices
