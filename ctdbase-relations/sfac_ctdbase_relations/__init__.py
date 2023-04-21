from Bio import Entrez
import pandas as pd
import io, json, re, requests, subprocess, sys, tarfile
import urllib.request
from xml.etree import ElementTree as ET

ENTREZ_EMAIL = 'support@insilica.co'

def distinct_pmids(df):
  all_ids = set()
  for row_set in df['PubMedIDs'].str.split('|').apply(set):
    all_ids.update(row_set)
  return all_ids

def rows_for_pubmed_id(df, pubmed_id):
  re_pubmed_id = re.compile(f"(^|\\|){pubmed_id}(\\||$)")
  return df[df['PubMedIDs'].fillna('').apply(lambda x: bool(re_pubmed_id.search(x)))]

def relations_for_pubmed_id(chem_df, pubmed_id):
  chem_df = rows_for_pubmed_id(chem_df, pubmed_id)
  relations = []
  for _, row in chem_df.head().iterrows():
    relations.append({
      'chemical': row['ChemicalName'],
      'chemical_id': row['ChemicalID'],
      'disease': row['DiseaseName'],
      'disease_id': row['DiseaseID'],
      'evidence': row['DirectEvidence']
    })
  return relations

def fetch_article(pmid):
    Entrez.email = ENTREZ_EMAIL
    handle = Entrez.efetch(db="pubmed", id=pmid, retmode="xml")
    records = Entrez.read(handle)
    handle.close()
    return records["PubmedArticle"][0]["MedlineCitation"]["Article"]

def article_abstract(article):
    if article.get('Abstract'):
      return article["Abstract"]["AbstractText"][0]

def article_title(article):
  return article['ArticleTitle']

def get_pmcid_from_pmid(pmid):
    Entrez.email = ENTREZ_EMAIL
    handle = Entrez.elink(dbfrom="pubmed", db="pmc", id=pmid)
    record = Entrez.read(handle)
    handle.close()

    try:
        pmcid = record[0]['LinkSetDb'][0]['Link'][0]['Id']
    except IndexError:
        return None

    return pmcid

def extract_text_from_element(element):
    text_parts = []
    for child in element.iter():
        if child.text and child.text.strip():
            text_parts.append(child.text.strip())

    return ' '.join(text_parts)

def get_full_text_from_xml(xml_content):
    root = ET.fromstring(xml_content)
    body = root.find('.//body')
    if body is None:
        return None

    full_text = extract_text_from_element(body)
    return full_text

def fetch_ftp(article_url, pmcid):
  try:
    with urllib.request.urlopen(article_url) as response:
        with io.BytesIO(response.read()) as file_obj:
            with tarfile.open(fileobj=file_obj, mode='r:gz') as tar:
                for member in tar.getmembers():
                    if member.name.endswith('.nxml'):
                        xml_file = tar.extractfile(member)
                        xml_content = xml_file.read().decode('utf-8')
                        return xml_content
  except urllib.error.URLError as e:
    print(f"Couldn't download the file for PMC ID: {pmcid}, error: {e}", file=sys.stderr)
    return None

def fetch_pmc_xml(pmcid):
    url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMC{pmcid}"
    response = requests.get(url)
    tree = ET.fromstring(response.content)

    for link in tree.findall('.//link'):
        if link.attrib['format'] == 'pdf':
            continue
        article_url = link.attrib['href']
        break
    else:
        return None

    if article_url.startswith('ftp'):
      return fetch_ftp(article_url, pmcid)
    else:
      full_text_response = requests.get(article_url)
      return full_text_response.text

def remove_nones(m):
  return {k: v for k, v in m.items() if v is not None}

def fetch_article_data(pubmed_id):
  pmcid = get_pmcid_from_pmid(pubmed_id)
  article = fetch_article(pubmed_id)
  text = None
  xml = fetch_pmc_xml(pmcid)
  if xml:
    text = get_full_text_from_xml(xml)

  return remove_nones({
    'abstract': article_abstract(article),
    'text': text,
    'title': article_title(article)
  })

def add_hash(event):
  process = subprocess.Popen("sr hash", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
  stdout, stderr = process.communicate(json.dumps(event))

  if process.returncode != 0:
    print(f"Error: {stderr.strip()}", file=sys.stderr)
    sys.exit(process.returncode)
  else:
    return json.loads(stdout.strip())

def print_events(label, chem_df, pubmed_id):
    try:
      data = fetch_article_data(pubmed_id)
    except Exception:
      return

    doc = add_hash({
      'data': data,
      'type': 'document',
      'uri': f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}"
    })
    print(json.dumps(doc))

    relations = relations_for_pubmed_id(chem_df, pubmed_id)
    answer = add_hash({
      'data': {
        'answer': relations,
        'document': doc['hash'],
        'label': label['hash'],
        'reviewer': 'https://github.com/insilica/sfac/ctdbase-relations'
      },
      'type': 'label-answer',
    })
    print(json.dumps(answer))

async def main():
  label = add_hash({
    'data': {
      'id': 'ctdbase-relations',
      'question': 'CTDBase Relations'
    },
    'type': 'label'
  })
  print(json.dumps(label))

  chem_df = pd.read_parquet('ctdbase/brick/CTD_chemicals_diseases.parquet')
  chem_df = chem_df[chem_df['DirectEvidence'].notna()]
  pmids = distinct_pmids(chem_df)

  for pubmed_id in pmids:
    print_events(label, chem_df, pubmed_id)

