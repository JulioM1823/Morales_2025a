'''
Purpose
-------
Read-only link, scope, and launch audit for generated managed HTML.

Inputs
------
None
    Test cases use local fixtures, parameterized inputs, and the imported
    implementation modules.

Outputs
-------
Tests and audit helpers: callable
    Expose the regression cases or measured audit entrypoints defined here.
'''
# Import the test dependencies and implementation modules used by these checks.
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit, parse_qs
import argparse
import json
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Time-Distance'))
import output_paths as paths
import comparison_gallery as gallery
from komega_bokeh_context import validate_context


class Links(HTMLParser):
    '''
    Purpose
    -------
    Collect local HTML resource references for the scope audit.

    Inputs
    ------
    None
        Constructed by the test framework or its enclosing fixture.

    Outputs
    -------
    instance: Links
        Fixture or test-suite object providing the documented methods.
    '''

    def __init__(self):
        '''
        Purpose
        -------
        Initialize HTMLParser state and an empty resource-link collection.

        Inputs
        ------
        None

        Outputs
        -------
        None
            Call HTMLParser.__init__() and create self.links as an empty list.
            Subsequent start-tag callbacks append nonempty href/src values.
        '''

        super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        '''
        Purpose
        -------
        Collect relevant resource paths from one HTML start tag.

        Inputs
        ------
        tag: str
            HTML start-tag name received by HTMLParser.

        attrs: list of tuple
            HTML attribute-name/value pairs received by HTMLParser.

        Outputs
        -------
        None
            Append matching src/href attribute values to the parser's reference list.
        '''

        self.links.extend(v for k,v in attrs if k in {'href','src'} and v)


def audit(root):
    '''
    Purpose
    -------
    Scan generated HTML pages for invalid local or cross-scope references.

    Inputs
    ------
    root: pathlib.Path
        Root directory containing the inputs, outputs, or cache under test.

    Outputs
    -------
    report: dict
        Audited page counts and detailed scope/resource failures.
    '''

    root=Path(root).absolute()
    counts=dict(html_pages=0,relative_links=0,subplot_targets=0,launch_contexts=0,comparison_images=0)
    failures=[]
    for page in root.rglob('*.html'):
        counts['html_pages']+=1
        text=page.read_text();parser=Links();parser.feed(text)
        for link in parser.links:
            if urlsplit(link).scheme or link.startswith('#'):
                continue
            target=page.parent/unquote(urlsplit(link).path)
            counts['relative_links']+=1
            if not target.is_file():failures.append(dict(page=str(page),missing=str(target)))
        match=re.search(r'const targets = (.*);',text)
        if match:
            for target in json.loads(match[1]):
                counts['subplot_targets']+=1
                source=page.parent/unquote(urlsplit(target['src']).path)
                if not source.is_file():failures.append(dict(page=str(page),missing=str(source)))
                workspace=target.get('bokeh',{}).get('workspace')
                if workspace:
                    counts['launch_contexts']+=1
                    try:
                        record=workspace['context'];validate_context(record)
                        encoded=json.loads(parse_qs(urlsplit(workspace['url']).query)['context'][0])
                        if encoded!=record:raise ValueError('URL and embedded context disagree')
                        if not Path(record['dataset']['file']).absolute().is_relative_to(root.parent/'Data'):
                            raise ValueError('Numerical launch reference is outside managed Data')
                    except (ValueError,KeyError,OSError) as exc:
                        failures.append(dict(page=str(page),context_error=str(exc)))
    for plot in gallery.discover_comparison_plots(root):
        counts['comparison_images']+=1
        record=json.loads(paths.find_json_sidecar(plot.path,'.subplots.json').read_text())
        scope=record['html_scope']
        for target in record['targets']:
            launch=target.get('bokeh',{}).get('workspace')
            if launch:
                value=launch['context'];identity=value['scope']
                if (identity['geometry']!=scope['geometry'] or identity['observable']!=scope['observable']
                    or identity['height_pair']['labels']!=scope['height_pair']['labels']):
                    failures.append(dict(plot=str(plot.path),scope_error=target['id']))
    return dict(counts=counts,failures=failures)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('--report',type=Path)
    args=parser.parse_args();result=audit(args.root)
    if args.report:paths.atomic_json(args.report,result)
    print(json.dumps({'counts':result['counts'],'failures':len(result['failures'])},indent=2))
    raise SystemExit(bool(result['failures']))
