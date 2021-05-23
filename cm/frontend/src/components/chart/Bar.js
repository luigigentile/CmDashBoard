import React from "react";
import { ResponsiveBar    } from '@nivo/bar'




// Bar Chart
//function BarChart(props) {

    class BarChart extends React.Component {
        constructor(props) {
          super(props);
          this.canvasRef = React.createRef();
        }
     


render() {

    return(
    <div style={{ height: this.props.height, width : this.props.height*2 }}>
      <h2 className = "ml-1"> {this.props.title}</h2>
      <ResponsiveBar  
        data={this.props.points}
        keys={[ 'Valori', ]}
        indexBy="Etichette"
        margin={{ top: 50, right: 130, bottom: 50, left: 60 }}
        padding={0.3}
        valueScale={{ type: 'linear' }}
        indexScale={{ type: 'band', round: true }}
        colors={{ scheme: 'category10' }}
        colorBy="index"
        
        theme=
           {{
                "background": "#061D36",
                "textColor": "white",
                "fontSize": 15,
                "axis": {
                    "domain": {
                        "line": {
                            "stroke": "#777777",
                            "strokeWidth": 1
                        }
                    },
                    "ticks": {
                        "line": {
                            "stroke": "#777777",
                            "strokeWidth": 1
                        }
                    }
                },
                "grid": {
                    "line": {
                        "stroke": "#dddddd",
                        "strokeWidth": 1
                    }
                }
            }}


        defs={[
            {
                id: 'dots',
                type: 'patternDots',
                background: 'inherit',
                color: '#38bcb2',
                size: 4,
                padding: 1,
                stagger: true
            },
            {
                id: 'lines',
                type: 'patternLines',
                background: 'inherit',
                color: '#eed312',
                rotation: -45,
                lineWidth: 6,
                spacing: 10
            }
        ]}


        fill={[
            {
                match: {
                    id: 'fries'
                },
                id: 'dots'
            },
            {
                match: {
                    id: 'sandwich'
                },
                id: 'lines'
            }
        ]}
        borderColor={{ from: 'color', modifiers: [ [ 'darker', 1.6 ] ] }}
        axisTop={null}
        axisRight={null}
        axisBottom={{
            tickSize: 5,
            tickPadding: 5,
            tickRotation: 0,
            legend: this.props.legend.titleAsseX,
            legendPosition: 'middle',
            legendOffset: 32
        }}
        axisLeft={{
            tickSize: 5,
            tickPadding: 5,
            tickRotation: 0,
            legend: this.props.legend.titleAsseY,
            legendPosition: 'middle',
            legendOffset: -40
        }}
        labelSkipWidth={12}
        labelSkipHeight={12}
        labelTextColor={this.props.legend.labelTextColor}
        legends={[
            {
                dataFrom: 'keys',
                anchor: 'bottom-right',
                direction: 'column',
                justify: false,
                translateX: 120,
                translateY: 0,
                itemsSpacing: 2,
                itemWidth: 100,
                itemHeight: 20,
                itemDirection: 'left-to-right',
                itemOpacity: 0.85,
                symbolSize: 20,
                effects: [
                    {
                        on: 'hover',
                        style: {
                            itemOpacity: 1
                        }
                    }
                ]
            }
        ]}
        legends = {[]}
        animate={true}
        motionStiffness={90}
        motionDamping={15}


        



    />

</div>
    )
    
  }
    }


  export default  function Bar(props) {
  var legends=[
    {
        dataFrom: 'keys',
        anchor: 'bottom-right',
        direction: 'column',
        justify: false,
        translateX: 120,
        translateY: 0,
        itemsSpacing: 2,
        itemWidth: 100,
        itemHeight: 20,
        itemDirection: 'left-to-right',
        itemOpacity: 0.85,
        symbolSize: 20,
        effects: [
            {
                on: 'hover',
                style: {
                    itemOpacity: 1
                }
            }
        ]
    }]

var points = []
var point = {}
var sumValori = 0
if (props.sons) {
for (var i=0;i<props.sons.length; i++) {
  point = {}
  point.Etichette = props.sons[i].label
  point.Valori = props.sons[i].allBlockCount
  point.color = "hsl(50, 40%, 50%)"
  if (point.Valori > 0) {
    points.push(point)
    sumValori = sumValori + props.sons[i].allBlockCount
    }
}

var title =  "Components by Categories"
}

return (
    <React.Fragment >
     {sumValori>0 ? <BarChart points = {points} legends = {legends} title = {props.title} height = {props.height} legend = {props.legend} />:null}
   </React.Fragment>
 );

}



