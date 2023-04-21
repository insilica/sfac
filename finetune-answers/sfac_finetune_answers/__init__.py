import json, sys

def write_train_data(doc, answers):
  data = doc.get('data', {})
  prompt = data.get('title', '') + '\n\n' + data.get('abstract', '') + '\n\n' + data.get('text', '')

  for answer in answers:
    print(json.dumps({'completion': json.dumps(answer['data']['answer']), 'prompt': prompt}))

def train(filename):
    with open(filename) as file:
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
    write_train_data(doc, answers)

async def main():
  train(sys.argv[1])

"""
nix run .#finetune-answers -- ../ctdbase-relations/train.jsonl > train.jsonl
rm train_prepared.jsonl
openai tools fine_tunes.prepare_data -f train.jsonl -q
openai api fine_tunes.create -t "train_prepared.jsonl" -m davinci
"""
