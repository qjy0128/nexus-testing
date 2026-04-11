from _bootstrap import bootstrap_paths

bootstrap_paths()

from nexus_testing.prepare_report_delivery import main

if __name__ == "__main__":
    raise SystemExit(main())
