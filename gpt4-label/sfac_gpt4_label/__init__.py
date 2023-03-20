from json.decoder import JSONDecodeError
from openai import ChatCompletion
import asyncio, json, jsonschema, math, openai, os, random, re, sys, tiktoken, time

MAX_INPUT_SIZE = 8191
SYSTEM_MESSAGE = {"role": "system", "content": "You are a ReviewGPT, a research assistant. Provide JSON data using only information from the schema and document. If you aren't sure of an answer, don't provide a value."}

def to_json(m):
  return json.dumps(m, separators=(',', ':'))

# I am going to try this for GPT-4 for now if we don't run into problems
def num_tokens_from_messages(messages, model="gpt-3.5-turbo-0301"):
  """Returns the number of tokens used by a list of messages."""
  try:
      encoding = tiktoken.encoding_for_model(model)
  except KeyError:
      encoding = tiktoken.get_encoding("cl100k_base")
  if model == "gpt-3.5-turbo-0301":  # note: future models may deviate from this
      num_tokens = 0
      for message in messages:
          num_tokens += 4  # every message follows <im_start>{role/name}\n{content}<im_end>\n
          for key, value in message.items():
              num_tokens += len(encoding.encode(value))
              if key == "name":  # if there's a name, the role is omitted
                  num_tokens += -1  # role is always required and always 1 token
      num_tokens += 2  # every reply is primed with <im_start>assistant
      return num_tokens
  else:
      raise NotImplementedError(f"""num_tokens_from_messages() is not presently implemented for model {model}.
  See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens.""")

def query(prompt, retry_sec=3):
  messages = [
    SYSTEM_MESSAGE,
    {"role": "user", "content": prompt}
  ]

  tokens = num_tokens_from_messages(messages)
  max_prompt_size = MAX_INPUT_SIZE - 1024
  if tokens >= max_prompt_size:
    reduction_ratio = max_prompt_size / tokens
    reduced_prompt_length = int(len(prompt) * (1 - reduction_ratio)) - 1
    prompt = prompt[:reduced_prompt_length]
    return query(MAX_INPUT_SIZE, prompt)
  else:
    try:
      return ChatCompletion.create(model="gpt-4", messages=messages)
    except openai.error.RateLimitError:
      retry_sec += 3 * random.random()
      time.sleep(retry_sec)
      query(prompt, 2 * retry_sec)

def clarify_answers(label, answers, msg):
  prompt = "Answer only with data that validates against this schema: " + to_json(label['json-schema'])
  prompt += "\nHere is the JSON data that must conform to the given schema: " + to_json(answers)
  prompt += "\nError message: " + msg
  q = query(prompt)
  if not q:
    return

  content = q['choices'][0]['message']['content'].strip()
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

def completions_to_answers(predictions, label):
  content = predictions['choices'][0]['message']['content'].strip()
  finish_reason = predictions['choices'][0]['finish_reason']
  if finish_reason == 'stop':
    try:
      answers = json.loads(content)
      try:
        jsonschema.validate(instance=answers, schema=label['json-schema'])
      except jsonschema.exceptions.ValidationError as e:
        return clarify_answers(label, answers, str(e))
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

def predict_doc(doc, label):
  json_schema = json.dumps(label['json-schema'], separators=(',', ':'))
  prompt = "Answer only in JSON that is valid according to this schema:" + json_schema
  prompt += "Document title: " + (doc['data']['title'] or '') + '\nAbstract: ' + (doc['data']['abstract'] or '')
  predictions = query(prompt)
  if predictions:
    return completions_to_answers(predictions, label)

def get_answer(doc, label, predictions, reviewer):
    data = {
      'answer': predictions,
      'document': doc['hash'],
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

async def main():
    limit = limit = 1024 * 1024 * 10 # Allow lines up to 10 MiB

    ihost,iport = os.environ["SR_INPUT"].split(":")
    sr_input, _ = await asyncio.open_connection(ihost, iport, limit=limit)

    ohost,oport = os.environ["SR_OUTPUT"].split(":")
    _, sr_output = await asyncio.open_connection(ohost, oport, limit=limit)

    config = json.load(open(os.environ['SR_CONFIG']))
    reviewer = config['reviewer']

    doc = None
    answers = []
    while True:
      line = await sr_input.readline()
      if not line:
        await sr_output.drain()
        break

      event = json.loads(line.decode().rstrip())
      if event['type'] == 'document':
        if doc:
          if not len(answers):
            results = []
            for label in config['current-labels']:
              if label['json-schema']:
                predictions = predict_doc(doc, label)
                answer = get_answer(doc, label, predictions, reviewer)
                if answer:
                  results.append(answer)
            if len(results):
              await write_events(sr_output, results)
        doc = event
        answers = []
        sr_output.write(line)
        await sr_output.drain()
      elif event['type'] == 'label-answer':
        answers.append(event)
        sr_output.write(line)
      else:
        sr_output.write(line)
        await sr_output.drain()
