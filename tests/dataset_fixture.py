"""Synthetic dataset only; callers own and remove the temporary root."""
import csv
from pathlib import Path

EVENT_FIELDS = 'event_id,event_name,domain,category,description,period,scope_include,scope_exclude,keywords,source_hints,status,owner,epg_path,gantt_path,review_path,notes'.split(',')
PERSON_FIELDS = 'person_id,name,aliases,coverage,research_plan,status,owner,notes'.split(',')
PROGRESS_FIELDS = 'person_id,storyline_id,storyline_name,event_id,event_name,period,status,owner,epg_path,gantt_path,review_path,notes'.split(',')


def csv_file(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for row in rows: writer.writerow(row)


def fixture_dataset(root):
    root = Path(root)
    csv_file(root / 'event-epg/events.csv', EVENT_FIELDS, [dict(event_id='EVENT-TEST', event_name='Synthetic acquisition',
        description='An invented deal for offline tests.', period='2020–2024', scope_include='The synthetic deal and closing',
        scope_exclude='Other deals', keywords='["deal, closing"]', source_hints='https://example.org/announcement', status='planned')])
    csv_file(root / 'person-epg/people.csv', PERSON_FIELDS, [dict(person_id='PERSON-TEST', name='Example Person',
        aliases='["E. Person"]', research_plan='Example Person/research-plan.md', status='planned')])
    csv_file(root / 'person-epg/Example Person/events.csv', PROGRESS_FIELDS, [dict(person_id='PERSON-TEST',
        storyline_id='STORY-TEST', storyline_name='Public service', event_id='PERSON-EVENT-TEST',
        event_name='Example appointment', period='1990s', status='planned')])
    plan = '''# Example Person: Research plan

## 1. person and research scope
| Field | Content |
| --- | --- |
| person_id | PERSON-TEST |

## 2. storyline catalog
| storyline_id | Name |
| --- | --- |
| STORY-TEST | Public service |

## 3. event master table
| event_id | Event name |
| --- | --- |
| PERSON-EVENT-TEST | Example appointment |

## 4. event research descriptions
### PERSON-EVENT-TEST · Example appointment
**Primary storyline:** STORY-TEST · Public service.
#### Event overview
An invented appointment [SRC01].
#### Connection to the person
The person accepted the appointment [SRC01].
#### Research scope
- **Activity period:** 1990s; exact dates unknown.
- **Included:** The appointment and term.
- **Excluded and related events:** Later offices.
#### Further research
- **Questions:** When did the term end?
- **Search leads:** Appointment notice [SRC01].
- **Open issues and decisions:** Exact dates unknown.

## 5. Coverage and matters awaiting confirmation
Pending.

## 6. Source index
| Source ID | Title and URL | Locator |
| --- | --- | --- |
| SRC01 | [Appointment](https://example.org/appointment) | Announcement |
| SRC02 | [Unrelated](https://example.org/other) | Unrelated source |

## 7. Handoff after confirmation
Pending confirmation.
'''
    (root / 'person-epg/Example Person/research-plan.md').write_text(plan, encoding='utf-8')
    return root
