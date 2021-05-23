import React from "react";
import { ResponsivePie } from '@nivo/pie'
import {ALL_MESSAGES} from '../../graphql'


import {
  useMutation,
  useQuery,
  gql
} from "@apollo/client";





// PieChart
class PieChart extends React.Component {
  constructor(props) {
    super(props);
    this.canvasRef = React.createRef();
  }


  render() {

  
  


    return(
    <div style={{ height: 300, width : 800 }}>
      <h2> PIE CHART </h2>
      <ResponsivePie
        data={this.props.points}
        margin={{ top: 40, right: 80, bottom: 80, left: 80 }}
        innerRadius={0.5}
        padAngle={0.7}
        cornerRadius={3}
        colors={{ scheme: 'nivo' }}
        borderWidth={1}
        borderColor={{ from: 'color', modifiers: [ [ 'darker', 0.2 ] ] }}
        radialLabelsSkipAngle={10}
        radialLabelsTextColor="#333333"
        radialLabelsLinkColor={{ from: 'color' }}
        sliceLabelsSkipAngle={10}
        sliceLabelsTextColor="#333333"
        defs={[
            {
                id: 'dots',
                type: 'patternDots',
                background: 'inherit',
                color: 'rgba(255, 255, 255, 0.3)',
                size: 4,
                padding: 1,
                stagger: true
            },
            {
                id: 'lines',
                type: 'patternLines',
                background: 'inherit',
                color: 'rgba(255, 255, 255, 0.3)',
                rotation: -45,
                lineWidth: 6,
                spacing: 10
            }
        ]}
        fill={[
            {
                match: {
                    id: 'ruby'
                },
                id: 'dots'
            },
            {
                match: {
                    id: 'c'
                },
                id: 'dots'
            },
            {
                match: {
                    id: 'go'
                },
                id: 'dots'
            },
            {
                match: {
                    id: 'python'
                },
                id: 'dots'
            },
            {
                match: {
                    id: 'scala'
                },
                id: 'lines'
            },
            {
                match: {
                    id: 'lisp'
                },
                id: 'lines'
            },
            {
                match: {
                    id: 'elixir'
                },
                id: 'lines'
            },
            {
                match: {
                    id: 'javascript'
                },
                id: 'lines'
            }
        ]}
        legends={[
            {
                anchor: 'bottom',
                direction: 'row',
                justify: false,
                translateX: 0,
                translateY: 56,
                itemsSpacing: 0,
                itemWidth: 100,
                itemHeight: 18,
                itemTextColor: '#999',
                itemDirection: 'left-to-right',
                itemOpacity: 1,
                symbolSize: 18,
                symbolShape: 'circle',
                effects: [
                    {
                        on: 'hover',
                        style: {
                            itemTextColor: '#000'
                        }
                    }
                ]
            }
        ]}
    />




     </div>
    )
    
  }
}

export default function ListaMessaggi() {
  const { loading, error,  data: allMessages } = useQuery(ALL_MESSAGES);

  var countedNames = allMessages.messages.reduce(function (allNames, name) {
    if (name.tipoMessaggio.tipo in allNames) {
      allNames[name.tipoMessaggio.tipo] ++;
    }
    else {
      allNames[name.tipoMessaggio.tipo] = 1;
    }
    return allNames;
  }, {});


var points = []
var point = {}
for (const key of Object.keys(countedNames)) {
  point = {}
  point.id = key
  point.label = key
  point.value = countedNames[key]
  point.color = "hsl(92, 70%, 50%)"
  points.push(point)

}



  console.log(points);
  

    return (
      
      <PieChart countedNames = {countedNames} points = {points} />
  
  );

 }
