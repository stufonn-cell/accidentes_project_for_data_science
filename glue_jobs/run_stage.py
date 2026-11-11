"""Glue job: runs one stage of the pipeline against the lake bucket.

Every Glue job of the stack uses this same script. The --stage argument
picks the module of src to run (bronze, silver, gold, models) and
--data_dir points config.DATA_DIR at the bucket. The src package arrives
as src.zip through --extra-py-files.
"""

import importlib
import os
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark import SparkContext

STAGES = {"bronze", "silver", "gold", "models", "expand"}

args = getResolvedOptions(sys.argv, ["JOB_NAME", "stage", "data_dir"])
if args["stage"] not in STAGES:
    raise ValueError(f"Unknown stage {args['stage']}, expected one of {sorted(STAGES)}")

glue = GlueContext(SparkContext.getOrCreate())
job = Job(glue)
job.init(args["JOB_NAME"], args)

# Must be set before src.config is imported: it reads DATA_DIR at import time
os.environ["DATA_DIR"] = args["data_dir"]
stage = importlib.import_module(f"src.{args['stage']}")
print(f"Running stage {args['stage']} with DATA_DIR={args['data_dir']}")
stage.main()

job.commit()
