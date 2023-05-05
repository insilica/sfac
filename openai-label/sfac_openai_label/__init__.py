from flask import Flask, request, jsonify
from json.decoder import JSONDecodeError
from openai import Completion
import pandas as pd
import argparse, asyncio, json, jsonschema, math, openai, os, random, re, sys, tiktoken, time

MAX_INPUT_SIZE = 2048
FINETUNED_MODEL = 'davinci:ft-https-insilica-co-2023-04-27-01-19-07'

def parse_args():
  parser = argparse.ArgumentParser(description='Use an OpenAI Completion model to create label-answers')
  parser.add_argument('--max_tokens', type=int, default=512)
  parser.add_argument('-m', '--model', type=str, default=FINETUNED_MODEL)
  parser.add_argument('-p', '--port', type=int, default=5000)
  parser.add_argument('--stop', type=str, default='"""')
  parser.add_argument('--temperature', type=float, default=0.0)
  return parser.parse_args()

def to_json(m):
  return json.dumps(m, separators=(',', ':'))

def srvc_version(config):
  version = config.get('config', {}).get('srvc', {}).get('version', None)
  if version:
    return list(map(int(version.split('.'))))

def srvc_0_18_or_later(config):
    version = srvc_version(config)
    if version:
        major, minor, _ = version
        return major > 0 or minor > 17
    return False

def num_tokens_from_messages(messages, model="davinci"):
  """Returns the number of tokens used by a list of messages."""
  encoding = tiktoken.encoding_for_model(model)
  return len(encoding.encode(messages))

def query(args, prompt, retry_sec=3):
  messages = prompt
  tokens = num_tokens_from_messages(messages)
  max_prompt_size = MAX_INPUT_SIZE - 1024
  if tokens >= max_prompt_size:
    reduction_ratio = max_prompt_size / tokens
    reduced_prompt_length = int(len(prompt) * (1 - reduction_ratio)) - 1
    prompt = prompt[:reduced_prompt_length]
    return query(args, prompt)
  else:
    try:
      return Completion.create(
        max_tokens=args.max_tokens,
        model=args.model,
        prompt=messages,
        stop=[args.stop] if args.stop else None,
        temperature=args.temperature
      )
    except openai.error.RateLimitError:
      retry_sec += 3 * random.random()
      time.sleep(retry_sec)
      query(prompt, 2 * retry_sec)

def clarify_answers(args, label, answers, msg):
  prompt = "Answer only with data that validates against this schema: " + to_json(label['json-schema'])
  prompt += "\nHere is the JSON data that must conform to the given schema: " + to_json(answers)
  prompt += "\nError message: " + msg
  q = query(args, prompt)
  if not q:
    return

  content = q['choices'][0]['text'].strip()
  finish_reason = q['choices'][0]['finish_reason']
  if finish_reason == 'stop':
    try:
      answers = json.loads(content)
      try:
        jsonschema.validate(instance=answers, schema=label['json-schema'])
      except jsonschema.exceptions.ValidationError as e:
        return []
      return answers
    except JSONDecodeError:
      # Sometimes GPT returns a prose answer stating that it has no answers
      return []
  elif finish_reason == 'length':
    # JSON truncated
    return []
  else:
    # No API response, or content omitted due to filters
    return []

def completions_to_answers(args, predictions, label):
  content = predictions['choices'][0]['text'].strip()
  finish_reason = predictions['choices'][0]['finish_reason']
  json_schema = label.get('json-schema')
  if finish_reason == 'stop':
    try:
      answers = json.loads(content)
      if json_schema:
        try:
          jsonschema.validate(instance=answers, schema=json_schema)
        except jsonschema.exceptions.ValidationError as e:
          return clarify_answers(args, label, answers, str(e))
      return answers
    except JSONDecodeError:
      # Sometimes GPT returns a prose answer stating that it has no answers
      return []
  elif finish_reason == 'length':
    # JSON truncated
    return []
  else:
    # No API response, or content omitted due to filters
    return []

def predict_doc(args, doc, label):
  data = doc.get('data', {})
  prompt = 'Label: ' + label['question'] + '\n\n' + (data.get('title') or '') + '\n\n' + (data.get('abstract') or '') + '\n\n' + (data.get('text') or '') + '\n\n###\n\n'

  predictions = query(args, prompt)
  if predictions:
    return completions_to_answers(args, predictions, label)

def chemical_id(chem_df, chemical_name):
  result = chem_df.loc[chem_df['ChemicalName'].str.lower() == chemical_name.lower(), 'ChemicalID']
  return next(iter(result), None) if isinstance(result, pd.Series) else result

def disease_id(disease_df, disease_name):
  result = disease_df.loc[disease_df['DiseaseName'].str.lower() == disease_name.lower(), 'DiseaseID']
  return next(iter(result), None) if isinstance(result, pd.Series) else result

def constrain_vocab(predictions, chem_df, disease_df):
  acc = []
  for p in predictions:
    p['chemical_id'] = chemical_id(chem_df, p['chemical'])
    p['disease_id'] = disease_id(disease_df, p['disease'])
    if p['chemical_id'] and p['disease_id']:
      acc.append(p)
  return acc

def get_answer(config, doc, label, predictions, reviewer):
    if srvc_0_18_or_later(config):
      eventProp = 'event'
    else:
      eventProp = 'document'

    data = {
      'answer': predictions,
      eventProp: doc['hash'],
      'label': label['hash'],
      'reviewer': reviewer,
      'timestamp': math.floor(time.time())
    }
    return {
      'data': data,
      'type': 'label-answer'
    }

async def write_events(stream, events):
    for event in events:
      s = json.dumps(event, separators=(',', ':'))
      stream.write(f"{s}\n".encode())

class AppConfig:
  def __init__(self, args, chem_df, disease_df):
    self.args = args
    self.chem_df = chem_df
    self.disease_df = disease_df

def create_app(config):
    app = Flask(__name__)
    app.config['app_config'] = config

    @app.route('/map', methods=['POST'])
    def process_json():
        data = request.get_json()
        if not data:
          return jsonify({"error": "Invalid JSON"}), 400

        appcfg = app.config['app_config']
        config = data['config']
        reviewer = config['reviewer']
        events = data['events']
        doc = events[0]

        for label in config['current-labels']:
          predictions = predict_doc(appcfg.args, doc, label)
          predictions = constrain_vocab(predictions, appcfg.chem_df, appcfg.disease_df)
          answer = get_answer(config, doc, label, predictions, reviewer)
          if answer:
            events.append(answer)

        return jsonify({'events': events})

    return app

async def main():
    args = parse_args()
    chem_df = pd.read_parquet('ctdbase-relations/ctdbase/brick/CTD_chemicals.parquet')
    disease_df = pd.read_parquet('ctdbase-relations/ctdbase/brick/CTD_diseases.parquet')
    config = AppConfig(args, chem_df, disease_df)
    app = create_app(config)
    app.run(debug=True, port=args.port)
