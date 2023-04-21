import argparse, json, sys

def write_train_data(doc, answers):
  data = doc.get('data', {})
  prompt = data.get('title', '') + '\n\n' + data.get('abstract', '') + '\n\n' + data.get('text', '')

  for answer in answers:
    print(json.dumps({'completion': json.dumps(answer['data']['answer']), 'prompt': prompt}))

def train(file):
  answers = []
  doc = None

  for line in file:
    if not line.strip():
        continue

    event = json.loads(line)
    if event['type'] == 'document':
      if doc:
        write_train_data(doc, answers)
      answers = []
      doc = event
    elif event['type'] == 'label-answer':
      answers.append(event)

  if doc:
    write_train_data(doc, answers)

def parse_args():
  parser = argparse.ArgumentParser(description='Create OpenAI fine-tuning data from SRVC events')
  parser.add_argument('train_file', type=str)
  return parser.parse_args()

async def main():
  args = parse_args()
  with open(args.train_file) as file:
    train(file)

"""
nix run .#finetune-answers -- ../ctdbase-relations/train.jsonl > train.jsonl
rm train_prepared.jsonl
openai tools fine_tunes.prepare_data -f train.jsonl -q
openai api fine_tunes.create -t "train_prepared.jsonl" -m davinci
"""
