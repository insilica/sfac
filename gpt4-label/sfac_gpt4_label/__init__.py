from json.decoder import JSONDecodeError
from openai import ChatCompletion
import asyncio, json, math, os, re, sys, tiktoken, time

SYSTEM_MESSAGE = {"role": "system", "content": "You are a ReviewGPT, a researcher who always gives answers that are valid according to the provided JSON schema. Provide JSON data using only information from the schema and document."}

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

def query( max_input_size, prompt):
  messages = [
    SYSTEM_MESSAGE,
    {"role": "user", "content": prompt}
  ]

  tokens = num_tokens_from_messages(messages)
  max_prompt_size = max_input_size - 1024
  if tokens >= max_prompt_size:
    reduction_ratio = max_prompt_size / tokens
    reduced_prompt_length = int(len(prompt) * (1 - reduction_ratio)) - 1
    prompt = prompt[:reduced_prompt_length]
    return query(max_input_size, prompt)
  else:
    return ChatCompletion.create(model="gpt-4", messages=messages)

def completions_to_answers(predictions, label):
  label_order = label['json-schema']['items']['srvcOrder']
  content = predictions['choices'][0]['message']['content'].strip()
  finish_reason = predictions['choices'][0]['finish_reason']
  if finish_reason == 'stop':
    try:
      return json.loads(content)
    except JSONDecodeError:
      # Sometimes gpt-3.5 returns a prose answer stating that it has no answers
      return []
  elif finish_reason == 'length':
    # JSON truncated
    return []
  else:
    # No API response, or content omitted due to filters
    return []

def predict_doc(max_input_size, doc, label):
  json_schema = '{"$id":"http://localhost:4061/web-api/srvc-json-schema?hash=QmQ4djRUAv7QmKL5KSZ3ZfvhRBBqgxcLjHyzXXf6uA4wVZ","type":"array","items":{"type":"object","srvcOrder":["stringwgdddI","categoricalLfOFUj","stringWODblq"],"properties":{"stringWODblq":{"type":"string","title":"Target","maxLength":100},"stringwgdddI":{"type":"string","title":"Source","maxLength":100},"categoricalLfOFUj":{"type":"array","items":{"enum":["inhibits","promotes"],"type":"string"},"title":"Relationship"}}},"title":"Relationships","$schema":"http://json-schema.org/draft-07/schema"}'
  prompt = "JSON schema:" + json_schema + '\n'
  prompt += "Document title: " + (doc['data']['title'] or '') + '\nAbstract: ' + (doc['data']['abstract'] or '')
  return completions_to_answers(query(max_input_size, prompt), label)

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
    label = config['current-labels'][0]
    reviewer = config['reviewer']

    max_input_size=8191

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
            predictions = predict_doc(max_input_size, doc, label)
            answer = get_answer(doc, label, predictions, reviewer)
            await write_events(sr_output, [answer])
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
