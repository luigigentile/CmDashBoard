import React from 'react';

import {ResponsiveLine} from "@nivo/line"

import {margin, volumevspricedata} from './VolumeVsPriceData'

// import {data} from './VolumeVsPriceData'


export default class BlocksVsCreated extends React.Component {
    constructor(props) {
        super(props);
        this.state = {messageSelected: "",
                 numeroLanci: 0};
       }
    
      
    render(){
        
         var dataBlock = this.props.data
         const commonProperties = {
            width: 800,
            height: 300,
            margin: { top: 20, right: 20, bottom: 60, left: 80 },
        }
        
        
//        animate: true,
//        enableSlices: 'x',
//

        const CustomSymbol = ({ size, color, borderWidth, borderColor }) => (
               <g>
                   <circle fill="#fff" r={size / 2} strokeWidth={borderWidth} stroke={borderColor} />
                   <circle
                       r={size / 5}
                       strokeWidth={borderWidth}
                       stroke={borderColor}
                       fill={color}
                       fillOpacity={0.35}
                   />
               </g>
           )
    
   
          var point = {
           "x":null,
           "y":null
        }
        var points = []

         function groupBy(objectArray, property) {
             return objectArray.reduce(function (acc, obj) {
               var key = obj[property];
               if (!acc[key]) {
                 acc[key] = 0;
                }
               acc[key] = acc[key]+1;
               return acc;
             }, {});
           }
          var groupedCreated = groupBy(dataBlock.allBlock, 'created');

          let yinitial = 0 
          for (let key of Object.keys(groupedCreated)) {
                point = {} 
                point.x =  key
                point.y = yinitial + groupedCreated[key]
                yinitial = point.y
                points.push(point)
             }
      
      console.log(points)
   
     var volumevspricedatan = [
         {
         id:"Blocks",
           data : points
         }
        ]
        
        console.log(volumevspricedatan)
        console.log(volumevspricedata)
        
//        useMesh={true}
  
return(
        <div style={{ height: this.props.height, width : this.props.width }}>
        <h1 className = "ml-3"> Blocks Number Vs Creation date </h1>
        <ResponsiveLine 
        {...commonProperties}
        data={volumevspricedatan}
        colors={{ scheme: 'category10' }}
        margin={margin}
        enablePoints = {false}
        enableGridX = {true}
       
        xScale={{
             type: 'time',
             format: '%Y-%m-%d',
             useUTC: false,
             precision: 'day',
           
         }}
         yScale={{
             type: 'linear',
             stacked: false,
             min : 'auto',
             max : 'auto'

         }}
         axisLeft={{
             legend: 'Blocks Number',
             legendPosition: 'end',
             tickValues: 5,
             legendOffset: -48,
         }}
         axisBottom={{
            format: '%Y-%m',
            tickValues: 'every 1 months',
            legend: 'Creation date',
            legendPosition: 'end',
            legendOffset: 36,
         }}
         curve='monotoneX'
         enablePointLabel={true}
         pointSymbol={CustomSymbol}
         pointSize={16}
         pointBorderColor={{
             from: 'color',
             modifiers: [['darker', 0.3]],
         }}
         
         enableSlices={false}
         isInteractive={true}
         useMesh ={false}
         

        onClick={() => console.log('clicked')}    
        onMouseEnter={node => console.log('mouseEntered]', node)}



                       
       
    />
     
 
 </div>
 );
    }
    
 }
