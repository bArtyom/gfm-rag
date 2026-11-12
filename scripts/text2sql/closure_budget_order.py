"""Column/connector accounting and conservative structural compatibility checks."""
from collections import deque
import sqlite3

import networkx as nx
import sqlglot
from sqlglot import exp
from seed_steiner import quote


def serialize_partial(schema,columns,constraints):
    selected=set(columns);definitions=schema['column_names_original']
    if any(c<0 or c>=len(definitions) or definitions[c][0]<0 for c in selected):raise ValueError('Unknown physical column')
    tables={definitions[c][0] for c in selected};lines=[]
    primary=[cid for entry in schema['primary_keys'] for cid in ([entry] if isinstance(entry,int) else entry)]
    for tid in sorted(tables):
        defs=[f'  {quote(name)} {schema["column_types"][cid]}' for cid,(owner,name) in enumerate(definitions) if owner==tid and cid in selected]
        pk=[c for c in primary if definitions[c][0]==tid]
        if pk and set(pk)<=selected:defs.append('  PRIMARY KEY ('+', '.join(quote(definitions[c][1]) for c in pk)+')')
        for f in constraints:
            if f['source_table']==tid and f['target_table'] in tables and all(a in selected and b in selected for a,b in f['pairs']):
                left=', '.join(quote(definitions[a][1]) for a,_ in f['pairs']);right=', '.join(quote(definitions[b][1]) for _,b in f['pairs'])
                defs.append('  FOREIGN KEY ('+left+') REFERENCES '+quote(schema['table_names_original'][f['target_table']])+' ('+right+')')
        lines.append('CREATE TABLE '+quote(schema['table_names_original'][tid])+' (\n'+',\n'.join(defs)+'\n);')
    return '\n'.join(lines)


class SchemaClosure:
    def __init__(self,schema,constraints):
        self.schema=schema;self.constraints=constraints;self.cache={}
        self.graph=nx.Graph();self.graph.add_nodes_from(range(len(schema['table_names_original'])))
        self.graph.add_edges_from(sorted({tuple(sorted((f['source_table'],f['target_table']))) for f in constraints if f['source_table']!=f['target_table']}))
        self.components=[set(c) for c in nx.connected_components(self.graph)]
        self.paths={}
        # Lexicographically smallest shortest paths, independent of edge insertion.
        for start in self.graph:
            found={start:(start,)};queue=deque([start])
            while queue:
                v=queue.popleft()
                for u in sorted(self.graph[v]):
                    if u not in found:found[u]=found[v]+(u,);queue.append(u)
            self.paths[start]=found

    def expand(self,columns):
        columns=set(columns);terminal={self.schema['column_names_original'][c][0] for c in columns}
        key=tuple(sorted(terminal))
        if key not in self.cache:
            tables=set(terminal)
            for component in self.components:
                terminals=terminal&component
                if not terminals:continue
                tree={min(terminals)}
                while not terminals<=tree:
                    _,_,path=min((len(self.paths[a][b])-1,b,self.paths[a][b]) for a in sorted(tree) for b in sorted(terminals-tree))
                    tree.update(path)
                tables.update(tree)
            fks=[f for f in self.constraints if f['source_table'] in tables and f['target_table'] in tables]
            keys={c for f in fks for pair in f['pairs'] for c in pair}
            self.cache[key]=(tables,fks,keys)
        tables,fks,keys=self.cache[key]
        return dict(columns=sorted(columns|keys),tables=sorted(tables),constraints=fks)


def select_columns(order,budget,expand,cost,mode):
    semantic=[];rejected=0;repairs=0
    for c in order:
        trial=semantic+[c];closed=expand(trial) if mode=='early' else None
        if cost(closed['columns'] if closed else trial,closed)<=budget:semantic=trial
        else:rejected+=1
    closed=expand(semantic);before=cost(closed['columns'],closed)
    while before>budget:
        if mode!='late' or not semantic:raise RuntimeError('Budget invariant failed')
        semantic.pop();repairs+=1;closed=expand(semantic);before=cost(closed['columns'],closed)
    return dict(**closed,semantic_columns=sorted(semantic),tokens=int(before),rejected_columns=rejected,repair_removals=repairs)


def expressibility(sql,schema,columns):
    """A one-sided structural witness, not execution or semantic accuracy."""
    try:
        tree=sqlglot.parse_one(sql,read='sqlite')
        if not isinstance(tree,exp.Query):return dict(status='unknown',reason='not_query')
        for star in tree.find_all(exp.Star):
            if not isinstance(star.parent,exp.Count):return dict(status='unknown',reason='projection_star')
        for col in tree.find_all(exp.Column):
            if not col.table and isinstance(col.this,exp.Identifier) and col.this.args.get('quoted'):
                return dict(status='unknown',reason='unqualified_quoted_column')
        for table in tree.find_all(exp.Table):
            if table.db or table.catalog:return dict(status='unknown',reason='qualified_catalog')
        for join in tree.find_all(exp.Join):
            if join.args.get('method')=='NATURAL' or join.args.get('using'):
                return dict(status='unknown',reason='natural_or_using')
        selected=set(columns);con=sqlite3.connect(':memory:')
        try:
            for tid,name in enumerate(schema['table_names_original']):
                defs=[quote(n)+' TEXT' for cid,(owner,n) in enumerate(schema['column_names_original']) if owner==tid and cid in selected]
                if defs:con.execute('CREATE TABLE '+quote(name)+' ('+', '.join(defs)+')')
            con.set_progress_handler(lambda:1,100000)
            con.execute('EXPLAIN QUERY PLAN '+sql).fetchall()
            return dict(status='compatible',reason='prepared')
        except sqlite3.Error as error:
            message=str(error)
            reason='missing_column' if 'no such column:' in message else 'missing_table' if 'no such table:' in message else 'other_prepare_error'
            return dict(status='incompatible',reason=reason)
        finally:con.close()
    except (sqlglot.errors.ParseError,ValueError,TypeError):return dict(status='unknown',reason='parse_error')


def reference_read_bindings(sql,schema):
    """Evaluation-only original physical read bindings from SQLite compilation."""
    names={n.casefold():t for t,n in enumerate(schema['table_names_original'])}
    ids={(t,n.casefold()):c for c,(t,n) in enumerate(schema['column_names_original']) if t>=0}
    tables=set();columns=set();unsupported=set();events=0
    con=sqlite3.connect(':memory:')
    try:
        for tid,name in enumerate(schema['table_names_original']):
            defs=[quote(n)+' TEXT' for owner,n in schema['column_names_original'] if owner==tid]
            con.execute('CREATE TABLE '+quote(name)+' ('+', '.join(defs)+')')
        def authorize(action,table,column,database,source):
            nonlocal events
            if action==sqlite3.SQLITE_READ:
                events+=1
                if table is None or table.casefold() not in names:unsupported.add('nonphysical_read');return sqlite3.SQLITE_OK
                tid=names[table.casefold()];tables.add(tid)
                if column:
                    key=(tid,column.casefold())
                    if key in ids:columns.add(ids[key])
                    else:unsupported.add('implicit_or_unknown_column')
            return sqlite3.SQLITE_OK
        con.set_authorizer(authorize);con.set_progress_handler(lambda:1,100000)
        con.execute('EXPLAIN QUERY PLAN '+sql).fetchall()
        return dict(status='unknown' if unsupported else 'ok',tables=sorted(tables),columns=sorted(columns),read_events=events,reasons=sorted(unsupported))
    except sqlite3.Error:return dict(status='unknown',tables=[],columns=[],read_events=events,reasons=['full_prepare_failure'])
    finally:con.close()
