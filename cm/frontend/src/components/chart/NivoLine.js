import React from "react";
import {ResponsiveLine} from "@nivo/line"
import Torta from './Torta'
import VolumeVsPrice from './VolumeVsPrice'
import {dataNivoLine} from './NivoLineData'



export default class NivoLine extends React.Component {
  
  constructor(props , context){
    super(props ,context);
    this.state = {
   
        }
    }
    
    render(){
     


   
      
      return(
        <div style={{ height: 400, width : 2000 }}>

             <div  className="row  border-bottom"   >
             <div className="col-lg-6 "   >   <Torta  /> </div>
             <div className="col-lg-6" >      <Bar  /> </div>
             </div>

             <div  className="row  mt-3 border-bottom "   >
             <div className="col-lg-6 "   >   <VolumeVsPrice  /> </div>
             <div className="col-lg-6 "   > 
        
                     <ResponsiveLine
                      data={dataNivoLine}
                      margin={{ top: 50, right: 110, bottom: 50, left: 60 }}
                      xScale={{ type: 'point' }}
                      yScale={{ type: 'linear', min: 'auto', max: 'auto', stacked: true, reverse: false }}
                      yFormat=" >-.2f"
                      axisTop={null}
                      axisRight={null}
                      axisBottom={{
                          orient: 'bottom',
                          tickSize: 5,
                          tickPadding: 5,
                          tickRotation: 0,
                          legend: 'transportation',
                          legendOffset: 36,
                          legendPosition: 'middle'
                      }}
                      axisLeft={{
                          orient: 'left',
                          tickSize: 5,
                          tickPadding: 5,
                          tickRotation: 0,
                          legend: 'count',
                          legendOffset: -40,
                          legendPosition: 'middle'
                      }}
                      pointSize={10}
                      pointColor={{ theme: 'background' }}
                      pointBorderWidth={2}
                      pointBorderColor={{ from: 'serieColor' }}
                      pointLabelYOffset={-12}
                      useMesh={true}
                      legends={[
                          {
                              anchor: 'bottom-right',
                              direction: 'column',
                              justify: false,
                              translateX: 100,
                              translateY: 0,
                              itemsSpacing: 0,
                              itemDirection: 'left-to-right',
                              itemWidth: 80,
                              itemHeight: 20,
                              itemOpacity: 0.75,
                              symbolSize: 12,
                              symbolShape: 'circle',
                              symbolBorderColor: 'rgba(0, 0, 0, .5)',
                              effects: [
                                  {
                                      on: 'hover',
                                      style: {
                                          itemBackground: 'rgba(0, 0, 0, .03)',
                                          itemOpacity: 1
                                      }
                                  }
                              ]
                          }
                      ]}
                  />
                  </div>
  </div>

            </div>
        );
    }
    
 }
