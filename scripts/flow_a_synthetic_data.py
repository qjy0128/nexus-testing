from _bootstrap import bootstrap_paths

bootstrap_paths()

from nexus_testing.flow_a_synthetic_data import main

if __name__ == "__main__":
    raise SystemExit(main())
