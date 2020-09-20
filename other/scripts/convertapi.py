#!/usr/bin/env python
"""
a helper script to change apis in the source
"""
import argparse
import subprocess

def main():
  """
  the main function
  """
  parser = argparse.ArgumentParser(description='convert APIs in source')
  parser.add_argument("original", help="the original api")
  parser.add_argument("new", help="the new api")
  parser.add_argument('-m', '--modify', action="store_true",
                      help="modify files", default=False)

  args = parser.parse_args()
  original = args.original
  new = args.new

  print 'original: ', original
  print 'new:      ', new

  files_found_cmd = "grep --include '*.py' -r \"'%s'\"" % original
  try:
    process_found = subprocess.check_output(files_found_cmd, shell=True)
    print process_found
  except subprocess.CalledProcessError:
    print 'no files match %s' % original

  if args.modify:
    cmd = "grep --include '*.py' -rl \"'%s'\" | xargs sed -i \"s/'%s'/'%s'/g\"" % \
                            (original, original, new)
    print cmd
    process = subprocess.call(cmd, shell=True)
    print process


if __name__ == '__main__':
  main()
