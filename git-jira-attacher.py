#!/usr/bin/env python

from __future__ import with_statement

import sys
import contextlib
import os
import os.path
import subprocess
import re
import collections
import getpass
import SOAPpy
import traceback
import pprint
import pdb


@contextlib.contextmanager
def with_mkdtemp(*args, **kwargs):
  import tempfile
  import shutil
  import traceback
  tmpdir = tempfile.mkdtemp(*args, **kwargs)
  try:
    yield tmpdir
  finally:
    shutil.rmtree(tmpdir)


def generate_patches(range, tmpdir):
  cmd = ["git", "format-patch", "--suffix=.txt", "-o", tmpdir, range]
  proc = subprocess.Popen(cmd,
      stdin=open("/dev/null"), stdout=subprocess.PIPE)
  (stdout, _) = proc.communicate()
  if proc.returncode != 0:
    raise subprocess.CalledProcessError(proc.returncode, cmd)
  return [ line for line in stdout.split("\n") if line ]


def get_issue_id(fname):
  id_re = re.compile(r'^\d+-([A-Z]+-\d+)\b')
  match = id_re.search(os.path.basename(fname))
  if match:
    return match.group(1)
  return None


def group_patches(patches):
  infos = [ (get_issue_id(p), p) for p in patches ]
  all_ids = [ id for (id, _) in infos if id ]

  if len(all_ids) == len(infos):
    # If each commit is tagged with an issue, great
    pass
  elif len(set(all_ids)) == 1:
    # If there is only one issue named in the commits, use that for all
    infos = [ (all_ids[0], fname) for (_, fname) in infos ]
  else:
    # Can't figure out where to upload the others
    raise Exception("Must have exactly one issue or an issue for each commit.  Parsed %s" % all_ids)

  grouped = collections.defaultdict(list)
  for id, fname in infos:
    grouped[id].append(fname)
  return grouped


def get_soap_client(base_url):
  base_url = base_url.rstrip("/")

  jirauser = getpass.getuser()
  jirapass = getpass.getpass()

  # Use urllib2 here instead of just passing the url directly,
  # because the internal urllib call seems to break with SSL+chunked.
  import urllib2
  handle = urllib2.urlopen(base_url + "/rpc/soap/jirasoapservice-v2?wsdl")
  client = SOAPpy.WSDL.Proxy(handle)
  auth = client.login(jirauser, jirapass)
  return client, auth


def confirm_attach(grouped_patches, soap_client, auth):
  for id, patches in sorted(grouped_patches.items()):
    issue = soap_client.getIssue(auth, id)
    print id, "(%s):" % issue["summary"]
    for patch in patches:
      print "  " + os.path.basename(patch)
  print

  while True:
    print "Continue? [y/n/x] ",
    resp = raw_input()
    if resp == "y": return True
    if resp == "n": return False
    if resp == "x": pdb.set_trace()


def attach_files(grouped_patches, soap_client, auth):
  all_okay = True

  for issue_id, patches in sorted(grouped_patches.items()):
    try:
      names = []
      datas = []
      for patch in patches:
        names.append(os.path.basename(patch))
        datas.append(SOAPpy.base64BinaryType(open(patch).read()))
      ret = soap_client.addAttachmentsToIssue(auth, issue_id, names, datas)
      if not ret:
        raise Exception("addAttachmentsToIssue returned false")
    except:
      all_okay = False
      traceback.print_exc()
    else:
      print "Successfully attached patch(es) to " + issue_id

  return all_okay


def generate_confirm_and_upload(base_url, range):
  with with_mkdtemp() as tmpdir:
    grouped_patches = group_patches(generate_patches(range, tmpdir))
    soap_client, auth = get_soap_client(base_url)
    if confirm_attach(grouped_patches, soap_client, auth):
      return attach_files(grouped_patches, soap_client, auth)


def main():
  if not (2 <= len(sys.argv) <= 3):
    sys.exit("usage: jira_patches.py GIT_RANGE [BASE_URL]")

  #base_url 'http://localhost:8080/"
  base_url = "https://issues.apache.org/jira/"
  if len(sys.argv) >= 3:
    base_url = sys.argv[2]
  range = sys.argv[1]

  ret = generate_confirm_and_upload(base_url, range)
  sys.exit(ret)


if __name__ == "__main__":
  main()
