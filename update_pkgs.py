#!/usr/bin/env python3
"""
Script to locally register or update packages in the index from GitHub release artifacts.
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".github"))
from actions import register, update, delete, sync_all

def main():
    # Register ggmlc with all release artifacts
    print("Registering ggmlc from monatis/ggmlc...")
    register(
        pkg_name="ggmlc",
        repo="monatis/ggmlc",
        tag="all",
        author="M. Yusuf Sarıgöz",
        short_desc="A multi-framework neural network compiler lowering PyTorch, JAX, Flax, and Keras models to portable, high-performance GGML execution",
        homepage="https://github.com/monatis/ggmlc"
    )
    print("ggmlc successfully indexed!")

if __name__ == "__main__":
    main()
