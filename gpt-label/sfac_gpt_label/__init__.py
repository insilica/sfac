from json.decoder import JSONDecodeError
from openai import ChatCompletion
import asyncio, json, math, os, re, sys, tiktoken, time

SYSTEM_MESSAGE = {"role": "system", "content": "You are a researcher who answers only in JSON arrays, no plaintext, without whitespace. Identify the susceptibility factors present in the document. Identify the source, nature of the relationship, and target. The only valid relationships are \"promotes\" and \"inhibits\". If you don't know any answers, write the empty array []. Example response: " + '[ { "source": "CEBPE gene promoter polymorphism (rs2239630 G > A)", "relationship": ["promotes"], "target": "B-cell acute lymphoblastic leukemia" } ]\n'}

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
  max_prompt_size = max_input_size - 512
  if tokens >= max_prompt_size:
    reduction_ratio = max_prompt_size / tokens
    reduced_prompt_length = int(len(prompt) * (1 - reduction_ratio)) - 1
    prompt = prompt[:reduced_prompt_length]
    return query(max_input_size, prompt)
  else:
    return ChatCompletion.create(model="gpt-3.5-turbo-0301", messages=messages)

def completions_to_answers(predictions, label):
  label_order = label['json-schema']['items']['srvcOrder']
  content = predictions['choices'][0]['message']['content'].strip()
  finish_reason = predictions['choices'][0]['finish_reason']
  if finish_reason == 'stop':
    try:
      raw_answers = json.loads(content)
    except JSONDecodeError:
      # Sometimes gpt-3.5 returns a prose answer stating that it has no answers
      return []
  elif finish_reason == 'length':
    # JSON truncated
    return []
  else:
    # No API response, or content omitted due to filters
    return []

  answers = []
  for row in raw_answers:
    answers.append({
      label_order[0]: row['source'],
      label_order[1]: row['relationship'],
      label_order[2]: row['target'],
    })
  return answers

def predict_doc(max_input_size, doc, label):
  prompt = "Document title: " + (doc['data']['title'] or '') + '\nAbstract: ' + (doc['data']['abstract'] or '')
  return completions_to_answers(query(max_input_size, prompt + json.dumps(doc, separators=(',', ':'))), label)

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
      'type':'label-answer'
    }

async def main():
    limit = limit = 1024 * 1024 * 10 # Allow lines up to 10 MiB

    ihost,iport = os.environ["SR_INPUT"].split(":")
    sr_input, _ = await asyncio.open_connection(ihost, iport, limit=limit)

    ohost,oport = os.environ["SR_OUTPUT"].split(":")
    _, sr_output = await asyncio.open_connection(ohost, oport, limit=limit)

    config = json.load(open(os.environ['SR_CONFIG']))
    label = config['current-labels'][0]
    reviewer = config['reviewer']

    max_input_size=4097

    doc = None
    answers = []
    while True:
      line = await sr_input.readline()
      if not line:
        await sr_output.drain()
        break

      sr_output.write(line)

      event = json.loads(line.decode().rstrip())

      if event['type'] == 'document':
        if doc:
          if not len(answers):
            predictions = predict_doc(max_input_size, doc, label)
            answer = json.dumps(get_answer(doc, label, predictions, reviewer), separators=(',', ':'))
            sr_output.write(f"{answer}\n".encode())
        doc = event
        answers = []
      elif event['type'] == 'label-answer':
        answers.append(event)
      else:
        await sr_output.drain()
