#!/usr/bin/env python3

import sys
from pathlib import Path
import shutil
import argparse
import subprocess
import yaml

PROJECT_ROOT = Path("/code")
SRC_DIR = PROJECT_ROOT / "src"
DOCS_DIR = PROJECT_ROOT / "docs"
FLUSH = True


def in_docker():
    """Returns: True if running in a docker container, else False"""
    try:
        with open("/proc/1/cgroup", "rt") as ifh:
            contents = ifh.read()
            return any([word in contents for word in ["actions_job", "docker"]])
    except OSError:
        return False


def run(cmd, cwd=PROJECT_ROOT, check_exit=True):
    p = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    while True:
        stdout = p.stdout.readline()
        if stdout == "" and p.poll() is not None:
            break
        if stdout:
            print(stdout, end="", flush=FLUSH)

    if check_exit and p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, " ".join(cmd))


def test(flags=None):

    cmd = ["pytest"]
    if flags is not None:
        cmd += flags

    run(cmd, cwd=PROJECT_ROOT)


def format_hdl(flags=None):
    """Format SystemVerilog and Verilog files"""

    # Use --inplace flag to overwrite existing files
    cmd = ["verible-verilog-format", "--inplace"]

    if flags is not None:
        cmd += flags

    # Add options from .verible-verilog-format.yaml if specified
    verible_verilog_format_yaml = PROJECT_ROOT / ".verible-verilog-format.yaml"
    yaml_data = None
    if verible_verilog_format_yaml.exists():
        with open(verible_verilog_format_yaml, "r") as f:
            yaml_data = yaml.safe_load(f.read())

    format_args = []
    for k, v in yaml_data.items():
        format_args.append(f"--{k}={v}")

    cmd += format_args

    # Add all SystemVerilog or Verilog files in any project directory
    hdl_search_patterns = ["**/*.sv", "**/*.v"]
    hdl_files = []
    for sp in hdl_search_patterns:
        hdl_files += PROJECT_ROOT.glob(sp)
    cmd += [str(f) for f in hdl_files]

    run(cmd)


def docs():
    """Make documentation"""

    DOCS_BUILD_DIR = DOCS_DIR / "build"

    # Delete entire docs build directory if it exists
    if DOCS_BUILD_DIR.exists():
        shutil.rmtree(DOCS_BUILD_DIR)

    # Create new docs build directory
    DOCS_BUILD_DIR.mkdir()

    # Generature SVG block diagram graphics
    generate_hdl_svgs()

    cmd = ["make", "html"]
    run(cmd, cwd=DOCS_DIR)


def generate_hdl_svgs():
    svg_path = DOCS_DIR / "source" / "svg"
    json_path = DOCS_DIR / "source" / "json"

    # Clear everything out of svg directory
    if svg_path.exists():
        shutil.rmtree(svg_path)
    svg_path.mkdir()

    # Create temporary json directory if it doesn't already exist
    if not json_path.exists():
        json_path.mkdir()

    # Add all SystemVerilog files in the src directory
    hdl_search_patterns = ["**/*.sv"]
    hdl_files = []
    for sp in hdl_search_patterns:
        hdl_files += SRC_DIR.glob(sp)

    print(hdl_files)

    # Ignore certain hdl files that fails svg generation despite
    # being synthesizable
    ignore_hdl_files = ["onehot_mux.sv"]
    hdl_files = [f for f in hdl_files if f.name not in ignore_hdl_files]

    print(hdl_files)

    svg_files = []
    json_files = []
    for f in hdl_files:
        svg_files += [svg_path / (f.stem + ".svg")]
        json_files += [json_path / (f.stem + ".json")]

    # Run yosys to output jsons and then use netlistsvg to create svgs for each module
    for i in range(len(hdl_files)):
        cmd = [
            "yosys",
            "-p",
            f"read -sv {hdl_files[i]}; proc; clean; json -o {json_files[i]}",
        ]
        run(cmd, cwd=DOCS_DIR)
        cmd = ["netlistsvg", f"{json_files[i]}", "-o", f"{svg_files[i]}"]
        run(cmd, cwd=DOCS_DIR)

    # Remove temporary json directory
    shutil.rmtree(json_path)


if __name__ == "__main__":

    # Parse input args
    parser = argparse.ArgumentParser()
    arg_list = [
        "--test",
        "--format",
        "--docs",
    ]
    for arg in arg_list:
        parser.add_argument(arg, action="store_true")
    args = parser.parse_args()

    # If no arguments are passed then do everything
    ALL = len(sys.argv) == 1

    # Check if in docker container
    if not in_docker():
        raise OSError(
            "Not in a docker container. This script must be run from within a docker container. See README.md for instructions."
        )
    else:

        # Resolve project root directory before proceeding
        if not PROJECT_ROOT.is_dir():
            raise FileNotFoundError(
                f"Cannot find project root directory: {PROJECT_ROOT}"
            )

        # Run test if --test
        if ALL or args.test:
            print("\nTesting...", flush=FLUSH)
            test()

        # Run format if --format
        if ALL or args.format:
            print("\nFormatting...", flush=FLUSH)
            format_hdl()

        # Run docs if --docs
        if ALL or args.docs:
            print("\nMaking documentation...", flush=FLUSH)
            docs()
