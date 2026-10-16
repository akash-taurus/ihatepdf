"""ihatepdf CLI — thin wrapper over core.ops. All local."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core import ops


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ihatepdf", description="Local-first PDF toolkit")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info", help="Show page count / metadata")
    s.add_argument("input")

    s = sub.add_parser("merge", help="Merge PDFs in order")
    s.add_argument("inputs", nargs="+")
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("split", help="Split PDF")
    s.add_argument("input")
    s.add_argument("-o", "--output-dir", required=True)
    s.add_argument("--ranges", default=None, help='"1-2,3-5" (default: one file per page)')
    s.add_argument("--every", type=int, default=None)

    s = sub.add_parser("extract", help="Extract pages")
    s.add_argument("input")
    s.add_argument("--pages", required=True, help='"1,3-5"')
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("delete", help="Delete pages")
    s.add_argument("input")
    s.add_argument("--pages", required=True)
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("rotate", help="Rotate pages")
    s.add_argument("input")
    s.add_argument("--angle", type=int, required=True, choices=[90, 180, 270, -90, -180, -270])
    s.add_argument("--pages", default=None)
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("reorder", help='Reorder pages, e.g. --order "3,1,2"')
    s.add_argument("input")
    s.add_argument("--order", required=True)
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("compress", help="Reduce file size")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--image-quality", type=int, default=65)
    s.add_argument("--dpi", type=int, default=150)

    s = sub.add_parser("images-to-pdf", help="Images -> PDF")
    s.add_argument("inputs", nargs="+")
    s.add_argument("-o", "--output", required=True)

    s = sub.add_parser("pdf-to-images", help="PDF -> images")
    s.add_argument("input")
    s.add_argument("-o", "--output-dir", required=True)
    s.add_argument("--dpi", type=int, default=200)
    s.add_argument("--format", default="png", choices=["png", "jpg"])
    s.add_argument("--pages", default=None)

    s = sub.add_parser("extract-images", help="Extract embedded images")
    s.add_argument("input")
    s.add_argument("-o", "--output-dir", required=True)

    s = sub.add_parser("watermark", help="Text watermark overlay")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--text", required=True)
    s.add_argument("--fontsize", type=int, default=48)
    s.add_argument("--pages", default=None)

    s = sub.add_parser("pagenumbers", help="Add page numbers")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--pages", default=None)

    s = sub.add_parser("encrypt", help="Encrypt PDF")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--password", required=True)

    s = sub.add_parser("decrypt", help="Decrypt PDF")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--password", required=True)

    s = sub.add_parser("text", help="Extract text to stdout")
    s.add_argument("input")
    s.add_argument("--pages", default=None)

    s = sub.add_parser("metadata", help="Get/set metadata")
    s.add_argument("input")
    s.add_argument("--set", nargs="*", default=None, metavar="k=v")
    s.add_argument("-o", "--output", default=None)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "info":
            print(json.dumps(ops.info(args.input), indent=2, default=str))
        elif args.cmd == "merge":
            print(ops.merge(args.inputs, args.output))
        elif args.cmd == "split":
            for f in ops.split_pdf(args.input, args.output_dir, args.ranges, args.every):
                print(f)
        elif args.cmd == "extract":
            print(ops.extract_pages(args.input, args.pages, args.output))
        elif args.cmd == "delete":
            print(ops.delete_pages(args.input, args.pages, args.output))
        elif args.cmd == "rotate":
            print(ops.rotate_pages(args.input, args.output, args.angle, args.pages))
        elif args.cmd == "reorder":
            print(ops.reorder_pages(args.input, args.order, args.output))
        elif args.cmd == "compress":
            print(
                json.dumps(
                    ops.compress_pdf(args.input, args.output, args.image_quality, args.dpi),
                    indent=2,
                )
            )
        elif args.cmd == "images-to-pdf":
            print(ops.images_to_pdf(args.inputs, args.output))
        elif args.cmd == "pdf-to-images":
            for f in ops.pdf_to_images(
                args.input, args.output_dir, args.dpi, args.format, args.pages
            ):
                print(f)
        elif args.cmd == "extract-images":
            for f in ops.extract_images(args.input, args.output_dir):
                print(f)
        elif args.cmd == "watermark":
            print(
                ops.watermark_text(
                    args.input, args.output, args.text, args.fontsize, pages=args.pages
                )
            )
        elif args.cmd == "pagenumbers":
            print(ops.add_page_numbers(args.input, args.output, pages=args.pages))
        elif args.cmd == "encrypt":
            print(ops.encrypt_pdf(args.input, args.output, args.password))
        elif args.cmd == "decrypt":
            print(ops.decrypt_pdf(args.input, args.output, args.password))
        elif args.cmd == "text":
            print(ops.extract_text(args.input, args.pages))
        elif args.cmd == "metadata":
            if args.set:
                md = dict(kv.split("=", 1) for kv in args.set)
                if not args.output:
                    print("--output required with --set", file=sys.stderr)
                    return 2
                print(ops.set_metadata(args.input, args.output, md))
            else:
                print(json.dumps(ops.get_metadata(args.input), indent=2, default=str))
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
