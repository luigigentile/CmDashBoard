import React from "react";
import { ResponsiveBar    } from '@nivo/bar'






// Bar Chart
class BarChart extends React.Component {
  constructor(props) {
    super(props);
    this.canvasRef = React.createRef();
  }


  render() {
    return(
      <div className = "ml-4">
    <div style={{ height: 600, width : 400 }}>
      <h2 className = "ml-4"> {this.props.title}</h2>
      <ResponsiveBar  
        data={this.props.points}
        keys={[ 'Valori', ]}
        indexBy="Etichette"
        margin={{ top: 50, right: 130, bottom: 50, left: 60 }}
        padding={0.3}
        valueScale={{ type: 'linear' }}
        indexScale={{ type: 'band', round: true }}
        colors={{ scheme: 'nivo' }}
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
            legend: 'Tipo Messaggio',
            legendPosition: 'middle',
            legendOffset: 32
        }}
        axisLeft={{
            tickSize: 5,
            tickPadding: 5,
            tickRotation: 0,
            legend: 'Number',
            legendPosition: 'middle',
            legendOffset: -40
        }}
        labelSkipWidth={12}
        labelSkipHeight={12}
        labelTextColor={{ from: 'color', modifiers: [ [ 'darker', 1.6 ] ] }}
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
     </div>
    )
    
  }
}

export default function Bar(props) {

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
for (var i=0;i<props.sons.length; i++) {
  point = {}
  point.Etichette = props.sons[i].label
  point.Valori = props.sons[i].allSonsCount
  point.color = "hsl(92, 70%, 50%)"
  points.push(point)
}
console.log(points);

var title =  "Components by Categories"


return (
  <div> 

   <BarChart points = {points} legends = {legends} title = {title} />
   </div>

  
  );

 }
