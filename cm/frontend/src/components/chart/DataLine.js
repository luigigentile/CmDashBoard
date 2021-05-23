

import React from "react";
import { Line } from '@nivo/line'



// PieChart
 export default class DataLine extends React.Component {
    constructor(props) {
    super(props);
    this.onClick = this.onClick.bind(this);
  }

  onClick() {
      alert("On click")
      }

  render() {

    
     const commonProperties = {
         width: 900,
         height: 400,
         margin: { top: 20, right: 20, bottom: 60, left: 80 },
         animate: true,
         enableSlices: 'x',
     }

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

     var points = []
     var point = {}
     // IMPOSTA LE CHIAVI
     var keys = ['blockType','count']
     var colors = ["hsl(92, 70%, 50%)","hsl(92, 40%, 20%)"]
     for (let i= 0; i < this.props.data.length; i++) {
            point = {}
            point.id =  this.props.data[i][keys[0]]
            point.label =  this.props.data[i][keys[0]]
            point.value = this.props.data[i][keys[1]]
            point.color = colors[i]
            points.push(point)
     }

// 
    return(
    <div style={{ height: 300, width : 800 }}>
    <h2> PIE CHART </h2>
    <Line 
    
         {...commonProperties}
         data={[
             {
                 id: 'fake corp. A',
                 data: [
                     { x: '2018-01-01', y: 7 },
                     { x: '2018-01-02', y: 5 },
                     { x: '2018-01-03', y: 11 },
                     { x: '2018-01-04', y: 9 },
                     { x: '2018-01-05', y: 12 },
                     { x: '2018-01-06', y: 16 },
                     { x: '2018-01-07', y: 13 },
                     { x: '2018-01-08', y: 13 },
                 ],
             },
             {
                 id: 'fake corp. B',
                 data: [
                     { x: '2018-01-04', y: 14 },
                     { x: '2018-01-05', y: 14 },
                     { x: '2018-01-06', y: 15 },
                     { x: '2018-01-07', y: 11 },
                     { x: '2018-01-08', y: 10 },
                     { x: '2018-01-09', y: 12 },
                     { x: '2018-01-10', y: 9 },
                     { x: '2018-01-11', y: 7 },
                 ],
             },
         ]}
         xScale={{
             type: 'time',
             format: '%Y-%m-%d',
             useUTC: false,
             precision: 'day',
         }}
         xFormat="time:%Y-%m-%d"
         yScale={{
             type: 'linear',
             stacked: true,
         }}
         axisLeft={{
             legend: 'linear scale',
             legendOffset: 12,
         }}
         axisBottom={{
             format: '%b %d',
             tickValues: 'every 2 days',
             legend: 'time scale',
             legendOffset: -12,
         }}
         

         curve='monotoneX'
         enablePointLabel={true}
         pointSymbol={CustomSymbol}
         pointSize={16}
         pointBorderWidth={1}
         pointBorderColor={{
             from: 'color',
             modifiers: [['darker', 0.3]],
         }}

         isInteractive={true}
         useMesh={true}
         enableSlices={false}
        
      
         
     />

   </div>
  )
  
}
 }



// import React, { Component, useState, useEffect } from 'react'
// import range from 'lodash/range'
// import last from 'lodash/last'
// import { storiesOf } from '@storybook/react'
// import { withKnobs, boolean, select } from '@storybook/addon-knobs'
// import { Defs, linearGradientDef } from '@nivo/core'
// import { area, curveMonotoneX } from 'd3-shape'
// import * as time from 'd3-time'
// import { timeFormat } from 'd3-time-format'
// import { Line } from '@nivo/line'
// 
// export default class DataLine extends React.Component {
// 
// constructor(props) {
//     super(props);
//   }
// 
// 
//   render() {
// const commonProperties = {
//     width: 900,
//     height: 400,
//     margin: { top: 20, right: 20, bottom: 60, left: 80 },
//     data,
//     animate: true,
//     enableSlices: 'x',
// }
// 
// const curveOptions = ['linear', 'monotoneX', 'step', 'stepBefore', 'stepAfter']
// 
// const CustomSymbol = ({ size, color, borderWidth, borderColor }) => (
//     <g>
//         <circle fill="#fff" r={size / 2} strokeWidth={borderWidth} stroke={borderColor} />
//         <circle
//             r={size / 5}
//             strokeWidth={borderWidth}
//             stroke={borderColor}
//             fill={color}
//             fillOpacity={0.35}
//         />
//     </g>
// )
// 
// return (
// <div>
// <Line
//         {...commonProperties}
//         data={[
//             {
//                 id: 'fake corp. A',
//                 data: [
//                     { x: '2018-01-01', y: 7 },
//                     { x: '2018-01-02', y: 5 },
//                     { x: '2018-01-03', y: 11 },
//                     { x: '2018-01-04', y: 9 },
//                     { x: '2018-01-05', y: 12 },
//                     { x: '2018-01-06', y: 16 },
//                     { x: '2018-01-07', y: 13 },
//                     { x: '2018-01-08', y: 13 },
//                 ],
//             },
//             {
//                 id: 'fake corp. B',
//                 data: [
//                     { x: '2018-01-04', y: 14 },
//                     { x: '2018-01-05', y: 14 },
//                     { x: '2018-01-06', y: 15 },
//                     { x: '2018-01-07', y: 11 },
//                     { x: '2018-01-08', y: 10 },
//                     { x: '2018-01-09', y: 12 },
//                     { x: '2018-01-10', y: 9 },
//                     { x: '2018-01-11', y: 7 },
//                 ],
//             },
//         ]}
//         xScale={{
//             type: 'time',
//             format: '%Y-%m-%d',
//             useUTC: false,
//             precision: 'day',
//         }}
//         xFormat="time:%Y-%m-%d"
//         yScale={{
//             type: 'linear',
//             stacked: boolean('stacked', false),
//         }}
//         axisLeft={{
//             legend: 'linear scale',
//             legendOffset: 12,
//         }}
//         axisBottom={{
//             format: '%b %d',
//             tickValues: 'every 2 days',
//             legend: 'time scale',
//             legendOffset: -12,
//         }}
//         curve={select('curve', curveOptions, 'monotoneX')}
//         enablePointLabel={true}
//         pointSymbol={CustomSymbol}
//         pointSize={16}
//         pointBorderWidth={1}
//         pointBorderColor={{
//             from: 'color',
//             modifiers: [['darker', 0.3]],
//         }}
//         useMesh={true}
//         enableSlices={false}
//     />
// </div>
//  ) }
// }