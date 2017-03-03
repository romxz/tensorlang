# Load graph, start a session, run it.

# vim: tabstop=2

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import json
import pprint
import re
import sys
import traceback

import graph_gen
import graph_io
import graph_query
import graph_xform
import graph_repl
import graph_execution

import tensorflow as tf

import subprocess

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def compile_meta_graph(input_json):
  with open(input_json, "r") as f:
    s = f.read()
    input_exprs = json.loads(s)
    # pp.pprint(input_exprs)

    return graph_gen.meta_graph_def_from_exprs(input_exprs)

def parse_packages(root, package_names):
  with subprocess.Popen(
      ["node", "lib/cli.js", "--root", root, "--parse=-", *package_names],
      stdout=subprocess.PIPE) as proc:
    expr_text = proc.stdout.read().decode('utf-8')
  return json.loads(expr_text)

def parse_source(root, source):
  with subprocess.Popen(
      ["node", "lib/cli.js", "--root", root, "--source", source, "--parse=-"],
      stdout=subprocess.PIPE) as proc:
    expr_text = proc.stdout.read().decode('utf-8')
  return json.loads(expr_text)

def main():
  parser = argparse.ArgumentParser()

  parser.add_argument("--root", type=str, default=".",
                      help="""Specify root directory to search for imports from""")
  parser.add_argument("--source", type=str,
                      help="""Specify source code instead of reading from file""")

  parser.add_argument("--metagraphdef", nargs='?', type=str,
                      help="""Graph file to load.""")
  parser.add_argument("--binary-metagraphdef", nargs='?', type=bool, default=False,
                      help="""Whether or not input is binary.""")
  parser.add_argument("--feed-constants", nargs='?', type=str,
                      help="""Path to GraphDef protobuf with constants to feed""")
  parser.add_argument("--feed-constants-strip", nargs='?', type=str, default="",
                      help="""Prefix to filter for (and strip from) constants""")
  parser.add_argument("--feed-constants-prefix", nargs='?', type=str,
                      help="""Prefix to add to constant names in feed""")
  parser.add_argument("--feed-constants-binary", nargs='?', type=bool, default=False,
                      help="""Whether or not feed constant protobuf is binary""")

  parser.add_argument("--run", nargs='?', type=bool, default=False,
                      help="""Run the graph with given (or default) --result* and --feed-* options""")
  parser.add_argument("--result-prefix", nargs='?', type=str, default="main/",
                      help="""Prefix of nodes to read result from.""")
  parser.add_argument("--result-binary", nargs='?', type=bool, default=False,
                      help="""Whether or not to result in binary.""")
  parser.add_argument("--result", nargs='?', type=str, default="/dev/stdout")

  parser.add_argument("--test", nargs='?', type=bool, default=False,
                      help="""Run the tests graphs with given (or default) --test-* options""")
  parser.add_argument("--test-result-pattern", nargs='?', type=str, default="^main/test[^/]*/([^_].*)$",
                      help="""Pattern to discover test graph results.""")

  parser.add_argument("--repl", nargs='?', type=bool, default=False,
                      help="""Start REPL""")

  parser.add_argument("--input-json", nargs='?', type=str,
                      help="""JSON file to load.""")

  parser.add_argument("--output-binary", nargs='?', type=bool, default=False,
                      help="""Whether or not to output in binary.""")
  parser.add_argument("--output-metagraphdef", nargs='?', type=str,
                      help="""Path to write output in.""")
  parser.add_argument("--output-graphdef", nargs='?', type=str,
                      help="""Path to write output in.""")

  FLAGS, package_names = parser.parse_known_args(args=sys.argv[1:])

  if FLAGS.test == None:
    FLAGS.test = True

  if FLAGS.run == None:
    FLAGS.run = True

  if FLAGS.repl == None:
    FLAGS.repl = True

  meta_graph_def = None

  if FLAGS.metagraphdef:
    meta_graph_def = graph_io.read_meta_graph_def(FLAGS.metagraphdef, FLAGS.binary_metagraphdef)

  if FLAGS.input_json:
    meta_graph_def = compile_meta_graph(FLAGS.input_json)

  if len(package_names) > 0 or FLAGS.source:
    if FLAGS.source:
      expressions = parse_source(FLAGS.root, FLAGS.source)
    else:
      expressions = parse_packages(FLAGS.root, package_names)

    meta_graph_def = graph_gen.meta_graph_def_from_exprs(expressions)

  if FLAGS.train:
    graph_execution.import_and_run_meta_graph(
      meta_graph_def=meta_graph_def,
      feed_dict={},
      result_pattern=re.compile(FLAGS.train_result_pattern),
    )

  if FLAGS.output_metagraphdef:
    graph_io.write_meta_graph_def(
      meta_graph_def=meta_graph_def,
      file=FLAGS.output_metagraphdef,
      binary=FLAGS.output_binary)

  if FLAGS.output_graphdef:
    graph_io.write_graph_def(
      graph_def=meta_graph_def.graph_def,
      file=FLAGS.output_graphdef,
      binary=FLAGS.output_binary)

  feed_dict = {}
  # Properly find and strip prefix of constants, loading them with given prefix to feed_dict
  if FLAGS.feed_constants:
    feed_graph_def = graph_io.read_graph_def(FLAGS.feed_constants, FLAGS.feed_constants_binary)
    constants = graph_query.find_nodes_with_prefix(feed_graph_def, FLAGS.feed_constants_strip)
    constants_dict = graph_xform.constants_as_dict(constants)
    strip_prefix = FLAGS.feed_constants_strip
    add_prefix = FLAGS.feed_constants_prefix
    for name, value in constants_dict.items():
      if strip_prefix != None:
        if name.startswith(strip_prefix):
          name = name[len(strip_prefix):]
        else:
          continue
      feed_dict[add_prefix + name + ":0"] = value

  if FLAGS.test:
    graph_execution.import_and_run_meta_graph(
      meta_graph_def=meta_graph_def,
      feed_dict={},
      result_pattern=re.compile(FLAGS.test_result_pattern),
    )

  if FLAGS.run:
    results = graph_execution.import_and_run_meta_graph(
      meta_graph_def=meta_graph_def,
      feed_dict=feed_dict,
      result_pattern=re.compile("^%s([^_].*)$" % FLAGS.result_prefix),
    )

    graph_def = graph_xform.dict_as_graph_def(results)
    graph_io.write_graph_def(
      graph_def,
      file=FLAGS.result,
      binary=FLAGS.result_binary,
    )

  if FLAGS.repl:
    graph_repl.run()

if __name__ == '__main__':
  try:
    main()
  except Exception as ex:
    # TODO(adamb) Should do *real* error printing.
    # NOTE(adamb) Need to correlate expressions with line and character numbers!
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
