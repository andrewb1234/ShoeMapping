from __future__ import annotations

import argparse

from personalization.jobs import process_next_pending_job, worker_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Process personalization jobs")
    parser.add_argument("--once", action="store_true", help="Process at most one pending job and exit")
    args = parser.parse_args()

    if args.once:
        process_next_pending_job()
        return
    worker_loop()


if __name__ == "__main__":
    main()
