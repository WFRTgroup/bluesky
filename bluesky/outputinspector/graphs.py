import dash_html_components as html
import dash_core_components as dcc
import pandas as pd
import plotly.graph_objects as go


def get_fire_label(fire):
    return ('fire ' + fire['flat_summary']['id'][0:5] + '...'
        + fire['flat_summary']['id'][-5:])

def generate_bar_graph_elements(graph_id, data, caption):
    return [
        dcc.Graph(
            id=graph_id,
            figure={
                'data': data,
                'layout': {
                    'clickmode': 'event+select',
                    'barmode':'group'
                }
            }
        ),
        html.Div(caption, className="caption")
    ]

def get_fuelbeds_graph_elements(summarized_fires):
    if not summarized_fires:
        return [html.Div("")]

    # TODO: make sure this handles multple selected fires
    data = []
    for f in summarized_fires:
        df = pd.DataFrame(f['fuelbeds'])
        if not df.empty:
            data.append(go.Bar(
                name=get_fire_label(f),
                x='fccs ' + df['fccs_id'], y=df['pct']
            ))

    if not data:
        return [html.Div("(no fuelbeds for fire)", className="empty-graph")]

    return generate_bar_graph_elements('fuelbeds-graph', data, "Fuelbeds")

def get_consumption_graph_elements(summarized_fires):
    if not summarized_fires:
        return [html.Div("")]

    # TODO: make sure this handles multple selected fires
    data = []
    for f in summarized_fires:
        df = pd.DataFrame([dict(c=c, v=v) for c,v in f['consumption_by_category'].items()])
        if not df.empty:
            data.append(go.Bar(name=get_fire_label(f), x=df['c'], y=df['v']))

    if not data:
        return [html.Div("(no fuelbeds for fire)", className="empty-graph")]

    return generate_bar_graph_elements('consumption-graph', data, "Consumption")

def get_emissions_graph_elements(summarized_fires):
    if not summarized_fires:
        return [html.Div("")]

    # timeprofiled emissions are summed across all locations, and
    # each species is graphed
    # Note that there should only be one fire
    # TODO: handle multple selected fires
    data = []
    for f in summarized_fires:
        df = pd.DataFrame(f['timeprofiled_emissions'])
        if not df.empty:
            species = [k for k in df.keys() if k != 'dt']
            for s in species:
                data.append({
                    'x': df['dt'],
                    'y': df[s],
                    'text': ['a', 'b', 'c', 'd'],
                    'customdata': ['c.a', 'c.b', 'c.c', 'c.d'],
                    'name': s,
                    'mode': 'lines+markers',
                    'marker': {'size': 5}
                })

    if not data:
        return [html.Div("(no emissions for fire)", className="empty-graph")]

    return [
        dcc.Graph(
            id='emissions-graph',
            figure={
                'data': data,
                'layout': {
                    # 'title': 'Emissions from fire(s) {}'.format(','.join(
                    #     f['flat_summary']['id'] for f in summarized_fires)),
                    'clickmode': 'event+select'
                }
            }
        ),
        html.Div("Timeprofiled Emissions", className="caption")
    ]

def get_plumerise_graph_elements(summarized_fires):
    if not summarized_fires:
        return [html.Div("")]

    return [html.Div("(plumerise graph coming soon)", className="empty-graph")]  # TEMP
