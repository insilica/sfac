import argparse, json, shlex, subprocess, sys, tempfile

def write_train_data(doc, answers, labels):
  data = doc.get('data', {})
  prompt = (data.get('title') or '') + '\n\n' + (data.get('abstract') or '') + '\n\n' + (data.get('text') or '')

  for answer in answers:
    label = labels[answer['data']['label']]
    print(json.dumps({
      'completion': json.dumps(answer['data']['answer']),
      'prompt': 'Label: ' + label['data']['question'] + '\n\n' + prompt
    }))

def train(file):
  answers = []
  doc = None
  labels = {}

  for line in file:
    if not line.strip():
        continue

    event = json.loads(line)
    if event['type'] == 'document':
      if doc:
        write_train_data(doc, answers, labels)
      answers = []
      doc = event
    elif event['type'] == 'label':
      labels[event['hash']] = event
    elif event['type'] == 'label-answer':
      answers.append(event)

  if doc:
    write_train_data(doc, answers, labels)

def parse_args():
  parser = argparse.ArgumentParser(description='Create OpenAI fine-tuning data from SRVC events')
  parser.add_argument('train_file', type=str)
  return parser.parse_args()

def pull_db(config_file, from_file, to_file):
  cmd = f"sr --config {shlex.quote(config_file)} pull {shlex.quote(from_file)} --db {shlex.quote(to_file)}"
  result = subprocess.run(cmd, shell=True, text=True, capture_output=True)

  if result.returncode != 0:
      print(f"Error in subprocess: {result.stderr}", file=sys.stderr)
      sys.exit(result.returncode)

async def main():
  args = parse_args()
  with tempfile.NamedTemporaryFile(delete=True, mode='w+', suffix='.yaml') as config_file:
    config_file.write("{reviewer: mailto:user@example.com}\n")
    config_file.flush()
    with tempfile.NamedTemporaryFile(delete=True, suffix='.jsonl') as temp_file:
      # jsonl files may not be in the right order, or the db may be a SQLite file.
      # Pulling the db ensures that we get a correctly ordered JSONL file.
      pull_db(config_file.name, args.train_file, temp_file.name)
      train(temp_file)

"""
nix run github:insilica/sfac#finetune-answers -- MY_SINK.db
"""

"""
nix run .#finetune-answers -- ../ctdbase-relations/train.jsonl > train.jsonl
rm train_prepared.jsonl
openai tools fine_tunes.prepare_data -f train.jsonl -q
openai api fine_tunes.create -t "train_prepared.jsonl" -m davinci
"""
