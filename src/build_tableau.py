"""Author a portable Tableau XML workbook and package its aggregate CSV sources.

The package is validated structurally. Tableau Desktop/Public is required to
verify rendering; no Tableau application is installed in the build environment.
"""
from pathlib import Path
import csv
import shutil
import zipfile
import xml.etree.ElementTree as E

ROOT=Path(__file__).resolve().parents[1]

def node(parent,tag,text=None,**attrs):
    element=E.SubElement(parent,tag,{k.replace('_','-'):str(v) for k,v in attrs.items()})
    if text is not None:element.text=text
    return element

SPECS=[
 ('funnel','Conversion funnel','stage','users','Bar',None),
 ('retention','Weekly cohort retention','cohort_week','week_number','Square','retention_rate'),
 ('segments','Early behavior and later purchase','segment','later_purchase_rate','Bar',None),
]

def build():
    folder=ROOT/'tableau';data=folder/'Data';data.mkdir(parents=True,exist_ok=True)
    workbook=E.Element('workbook',{'version':'10.5','source-platform':'mac','original-version':'10.5'})
    node(workbook,'preferences')
    sources=node(workbook,'datasources')
    columns={}
    for name,_,row,col,mark,color in SPECS:
        shutil.copyfile(ROOT/'data/processed'/f'{name}.csv',data/f'{name}.csv')
        if name=='funnel':
            with (data/f'{name}.csv').open() as handle:
                records=list(csv.DictReader(handle))
            for record in records:record['stage']=f"{record['stage_order']}. {record['stage']}"
            with (data/f'{name}.csv').open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(records[0]))
                writer.writeheader();writer.writerows(records)
        with (data/f'{name}.csv').open() as f:headers=next(csv.reader(f))
        ds=node(sources,'datasource',caption=name.replace('_',' ').title(),inline='true',name=name,version='10.5')
        conn=node(ds,'connection',directory='Data',filename=f'{name}.csv',server='')
        conn.set('class','textscan')
        relation=node(conn,'relation',name=f'{name}.csv',table=f'[{name}.csv]',type='table')
        relation_columns=node(relation,'columns',header='yes',separator=',',locale='en_US')
        columns[name]={}
        for index,header in enumerate(headers):
            string=header in {'stage','cohort_week','feature','segment'}
            datatype='string' if string else 'real' if 'rate' in header else 'integer'
            dimension=string or header in {'stage_order','week_number','fully_observed','complete_acquisition_week'}
            attrs={'datatype':datatype,'name':f'[{header}]','role':'dimension' if dimension else 'measure','type':'nominal' if string else 'ordinal' if dimension else 'quantitative'}
            node(relation_columns,'column',datatype=datatype,name=header,ordinal=index)
            element=node(ds,'column',**attrs)
            if 'rate' in header:element.set('default-format','p0.1%')
            columns[name][header]=attrs
    worksheets=node(workbook,'worksheets')
    for source,title,row,col,mark,color in SPECS:
        ws=node(worksheets,'worksheet',name=title)
        layout=node(ws,'layout-options');title_element=node(layout,'title')
        node(node(title_element,'formatted-text'),'run',title)
        table=node(ws,'table');view=node(table,'view')
        node(node(view,'datasources'),'datasource',caption=source.replace('_',' ').title(),name=source)
        deps=node(view,'datasource-dependencies',datasource=source)
        references={}
        for header in dict.fromkeys([row,col]+([color] if color else [])):
            attrs=columns[source][header]
            node(deps,'column',**attrs)
            dimension=attrs['role']=='dimension'
            derivation='None' if dimension else 'Avg' if 'rate' in header else 'Sum'
            suffix='nk' if attrs['datatype']=='string' else 'ok' if dimension else 'qk'
            instance=f'[{derivation.lower()}:{header}:{suffix}]'
            node(deps,'column-instance',column=f'[{header}]',derivation=derivation,name=instance,pivot='key',type=attrs['type'])
            references[header]=f'[{source}].{instance}'
        node(view,'aggregation',value='true')
        node(table,'style')
        pane=node(node(table,'panes'),'pane')
        node(node(pane,'view'),'breakdown',value='auto')
        m=node(pane,'mark');m.set('class',mark)
        enc=node(pane,'encodings')
        if color:node(enc,'color',column=references[color])
        if mark=='Bar':node(enc,'text',column=references[col])
        node(table,'rows',references[row]);node(table,'cols',references[col])
    dashboards=node(workbook,'dashboards')
    dashboard=node(dashboards,'dashboard',name='Product conversion and retention')
    node(dashboard,'style');node(dashboard,'size',maxheight=900,maxwidth=1400,minheight=900,minwidth=1400)
    zones=node(dashboard,'zones');container=node(zones,'zone',type='layout-basic',h=100000,w=100000,x=0,y=0,id=0)
    for i,(_,title,*_) in enumerate(SPECS):
        x,y,w,h=[(1000,1000,48000,43000),(1000,46000,98000,53000),(51000,1000,48000,43000)][i]
        zone=node(container,'zone',h=h,w=w,x=x,y=y,id=i+1,name=title)
        node(node(zone,'zone-style'),'format',attr='margin',value=8)
    E.indent(workbook)
    file=folder/'product_funnel.twb'
    E.ElementTree(workbook).write(file,encoding='utf-8',xml_declaration=True)
    with zipfile.ZipFile(folder/'product_funnel.twbx','w',compression=zipfile.ZIP_DEFLATED) as package:
        package.write(file,file.name)
        for path in sorted(data.glob('*.csv')):package.write(path,f'Data/{path.name}')
    validate(folder/'product_funnel.twbx')
    print('Built and structurally validated tableau/product_funnel.twbx')

def validate(package):
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        tree=E.fromstring(archive.read('product_funnel.twb'))
        sheets={s.attrib['name'] for s in tree.findall('worksheets/worksheet')}
        assert len(sheets)==3
        for connection in tree.findall('datasources/datasource/connection'):
            name=f"{connection.attrib['directory']}/{connection.attrib['filename']}"
            assert name in archive.namelist()
        for zone in tree.findall('.//dashboard/zones/zone/zone'):
            assert zone.attrib['name'] in sheets

if __name__=='__main__':build()
