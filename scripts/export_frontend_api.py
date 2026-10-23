#!/usr/bin/env python3
"""Export OpenAPI, TypeScript and validate captured real API fixtures."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from lexicon_search.api import create_app
from frontend_api_contracts import RESPONSES, ErrorResponse


def route_template(path):
    if re.fullmatch(r'/entries/\d+',path):
        return '/entries/{lemma_id}'
    if re.fullmatch(r'/senses/\d+/examples',path):
        return '/senses/{sense_id}/examples'
    return path


def ts_type(schema):
    if '$ref' in schema:
        return schema['$ref'].rsplit('/',1)[-1]
    if 'anyOf' in schema or 'oneOf' in schema:
        return ' | '.join(ts_type(s) for s in schema.get('anyOf',schema.get('oneOf')))
    if 'const' in schema:
        return json.dumps(schema['const'],ensure_ascii=False)
    if 'enum' in schema:
        return ' | '.join(json.dumps(s,ensure_ascii=False) for s in schema['enum'])
    kind = schema.get('type')
    if kind == 'array': return 'Array<'+ts_type(schema['items'])+'>'
    if kind == 'object':
        if 'properties' in schema:
            required = schema.get('required',[])
            return '{ '+ '; '.join(k+('' if k in required else '?')+': '+ts_type(v)
                for k,v in schema['properties'].items())+' }'
        additional = schema.get('additionalProperties',{})
        return 'Record<string, '+(ts_type(additional) if isinstance(additional,dict) else 'unknown')+'>'
    return {'string':'string','integer':'number','number':'number','boolean':'boolean','null':'null'}.get(kind,'unknown')


def export(destination):
    spec = create_app().openapi()
    spec['info'].update(description='荷兰语词典后端接口。公网部署尚未完成；Key仅在后端保存。',
                        **{'x-contract-revision':'2026-10-23'})
    spec['servers'] = [{'url':'http://127.0.0.1:8799','description':'离线响应回放服务，仅支持已录制场景'},
                       {'url':'http://127.0.0.1:8080','description':'本地真实后端示例地址，需自行启动'}]
    spec['security'] = []
    schemas = spec.setdefault('components',{}).setdefault('schemas',{})
    for model in [*RESPONSES.values(),ErrorResponse]:
        schema = model.model_json_schema(ref_template='#/components/schemas/{model}')
        schemas.update(schema.pop('$defs',{}))
        schemas[model.__name__] = schema
    descriptions = {
        '/lookup':('lookup','普通查词','精确词头/词形优先，未命中时纠错；不调用云模型。'),
        '/suggest':('suggest','输入联想','前缀匹配，不足时模糊补足；不调用云模型。'),
        '/entries/{lemma_id}':('getEntry','词条详情','四组独立分页；语料例句未经义项消歧；保留来源与审核状态。'),
        '/senses/{sense_id}/examples':('getSenseExamples','义项例句','有效例句和已有译文的分页读取。'),
        '/semantic-search':('semanticSearch','按含义找词','直接Flash改写后进行v4检索；失败时原文回退，预算不足503；每次可能产生费用。'),
        '/health':('health','内部健康检查','Nginx公网模板屏蔽此路径，前端无需轮询。'),
    }
    for path, model in RESPONSES.items():
        method = 'post' if path == '/semantic-search' else 'get'
        operation = spec['paths'][path][method]
        opid,title,description = descriptions[path]
        operation.update(operationId=opid,summary=title,description=description,
            tags=['内部' if path == '/health' else ('查词' if path in ('/lookup','/suggest','/semantic-search') else '详情')])
        operation['responses']['200'] = {'description':'成功','content':{'application/json':{
            'schema':{'$ref':'#/components/schemas/'+model.__name__}}}}
        statuses = [503] if path == '/health' else [413,429,503]
        if path.startswith(('/entries/','/senses/')): statuses.append(404)
        for status in statuses:
            operation['responses'][str(status)] = {'description':{
                404:'不存在或不对外显示',413:'请求体超过8 KiB',429:'单IP限流；代理层可能返回非JSON',503:'功能未开启、供应商/数据库不可用或预算不允许'}[status],
                'content':{'application/json':{'schema':{'$ref':'#/components/schemas/ErrorResponse'}}}}
            if status == 429:
                operation['responses']['429']['headers'] = {'Retry-After':{'description':'应用层返回的等待秒数；代理层可能不含此头',
                    'schema':{'type':'integer','minimum':1}}}
        if path != '/health':
            operation['responses']['422'] = {'description':'参数校验失败，或配置结果数上限校验失败',
                'content':{'application/json':{'schema':{'oneOf':[
                    {'$ref':'#/components/schemas/HTTPValidationError'},
                    {'$ref':'#/components/schemas/ErrorResponse'}]}}}}
            operation['x-rate-limit'] = {'shared_requests_per_minute':60,'shared_burst_per_10s':10,
                                         'semantic_requests_per_minute':10 if method=='post' else None}
    manifest_path = destination/'mock/manifest.json'
    validations = []
    if manifest_path.exists():
        scenarios = json.loads(manifest_path.read_text())['scenarios']
        preferred=['zh-website-rewrite','en-website-rewrite','nl-website-rewrite','nl-wheelchair-rewrite',
                   'lookup-huizen','lookup-typo','lookup-empty','lookup-huis','suggest-hui','suggest-empty',
                   'entry-138','entry-1','entry-8','entry-afzetten-page-7',
                   'sense-examples','sense-examples-page-0','sense-examples-page-4','sense-examples-empty-page']
        priority={name:index for index,name in enumerate(preferred)}
        scenarios=sorted(scenarios,key=lambda s:(priority.get(s['id'],999),not s.get('default_replay',False),s['id']))
        for scenario in scenarios:
            request,response = scenario['request'],scenario['response']
            body = json.loads((destination/response['body_file']).read_text())
            path = route_template(request['path'])
            model = RESPONSES[path]
            if response['status'] == 200:
                model.model_validate(body,strict=True)
                op = spec['paths'][path][request['method'].lower()]
                examples = op['responses']['200']['content']['application/json'].setdefault('examples',{})
                if len(examples)<4:
                    examples[scenario['id']] = {'summary':scenario['title'],'externalValue':response['body_file']}
            else:
                assert 'detail' in body and isinstance(body['detail'],(str,list))
                if isinstance(body['detail'],str): ErrorResponse.model_validate(body,strict=True)
            validations.append({'id':scenario['id'],'status':'passed','http_status':response['status']})
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'openapi.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
    try:
        import yaml
        class Dumper(yaml.SafeDumper):
            def ignore_aliases(self,data): return True
        (destination/'openapi.yaml').write_text(yaml.dump(spec,Dumper=Dumper,allow_unicode=True,sort_keys=False))
    except ImportError:
        pass
    lines = ['// Generated from openapi.json. IDs are JSON integers; current IDs fit JavaScript safe integers.','']
    for name,schema in sorted(schemas.items()):
        if schema.get('type')=='object' and 'properties' in schema:
            lines.append('export interface '+name+' {')
            required=schema.get('required',[])
            for key,value in schema['properties'].items():
                if value.get('description'): lines.append('  /** '+value['description'].replace('*/','* /')+' */')
                lines.append('  '+key+('' if key in required else '?')+': '+ts_type(value)+';')
            lines.append('}')
        else:
            lines.append('export type '+name+' = '+ts_type(schema)+';')
        lines.append('')
    (destination/'types.ts').write_text('\n'.join(lines))
    (destination/'reports/contract-validation.json').parent.mkdir(exist_ok=True)
    (destination/'reports/contract-validation.json').write_text(json.dumps({
        'status':'passed','validated_scenarios':len(validations),'checks':validations},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(destination),'schemas':len(schemas),'validated_scenarios':len(validations)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/frontend_api_handoff_20261023')
    export(parser.parse_args().output)
