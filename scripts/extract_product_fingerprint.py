from _bootstrap import bootstrap_paths

bootstrap_paths()

from nexus_testing.extract_product_fingerprint import main

if __name__ == "__main__":
    raise SystemExit(main())
