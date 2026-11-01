import os

# faiss-cpu and torch each ship their own OpenMP runtime on macOS; loading both segfaults (exit 139)
# unless duplicates are allowed and OpenMP runs single-threaded. Set before either library is imported.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
