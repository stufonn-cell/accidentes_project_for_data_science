"""Glue job: runs one stage of the pipeline against the lake bucket.

Every job of the stack (except ingestion, a Python shell job of its own)
uses this same script. The --stage argument picks the stage and
--data_dir is the lake bucket. The code arrives as src.zip through
--extra-py-files.

All stages run the same pandas modules of src that run locally
(src.bronze, src.silver, src.gold, src.models, src.tablero, src.expand), on the Glue driver: the
RUNT table has about 450 thousand rows and fits in memory. Distributed
processing with Spark DataFrames is a pending item.
"""

import importlib
import os
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark import SparkContext

STAGES = {"bronze", "silver", "gold", "models", "tablero", "expand"}

args = getResolvedOptions(sys.argv, ["JOB_NAME", "stage", "data_dir"])
stage = args["stage"]
if stage not in STAGES:
    raise ValueError(f"Unknown stage {stage}, expected one of {sorted(STAGES)}")

glue = GlueContext(SparkContext.getOrCreate())
job = Job(glue)
job.init(args["JOB_NAME"], args)

print(f"Running stage {stage} with data_dir={args['data_dir']}")
# Must be set before src.config is imported: it reads DATA_DIR at import time
os.environ["DATA_DIR"] = args["data_dir"]
importlib.import_module(f"src.{stage}").main()

job.commit()
