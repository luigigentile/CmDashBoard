import React, { useState } from 'react';

import {useQuery} from "@apollo/client";
import {connect } from 'react-redux'
import {ALL_MANUFACTURER} from '../graphql'
import ManufacturerItem from './ManufacturerItem'
import ManufacturerSelect from './ManufacturerSelect'

import BarChart from './chart/BarChart'


function ManufacturerList(props) {
// manufacturers = all manufacter that derve from Manufacturer table
// manufacturersOrders = the manufacturers list order by partCount


const { loading, error,  data:allManufacturer } = useQuery(ALL_MANUFACTURER);
if (loading) return <p>Loading...</p>;
if (error) return <p>Errore nel caricare la pagina  :</p>;

let manufacturers = allManufacturer.allManufacturer



var manufacturersOrders = []
var OthersPartCount = 0
var totalPartCount = 0
for (var i = 0 ; i<manufacturers.length ; i++){
  totalPartCount = totalPartCount + manufacturers[i].partCount
  if (manufacturers[i].partCount > props.minManufacturerCount) {
    manufacturersOrders.push(manufacturers[i])
  }
  else {
    OthersPartCount = OthersPartCount +manufacturers[i].partCount
  }
}

const OthersItem = {
  name : 'Others',
  partCount : OthersPartCount
}
 manufacturersOrders.sort((firstItem, secondItem) =>   secondItem.partCount - firstItem.partCount);

manufacturersOrders.push(OthersItem)
 

   const manufacturerList = manufacturersOrders.map((x) => {
     return (
    <ManufacturerItem manufacturer = {x}  totalPartCount = {totalPartCount}/> 
     )}
 );

 
 
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
 for (i=0;i<manufacturersOrders.length; i++) {
   point = {}
   point.Etichette = manufacturersOrders[i].name.substr(0,10)
   point.Valori = manufacturersOrders[i].partCount
   point.color = "hsl(92, 70%, 50%)"
   points.push(point)
 }
 
 var title =  "Components by Manufacturer"
 var height = 800
 var legend = {
   titleAsseX : "Manufacturer",
   titleAsseY : "Components' Number",
   labelTextColor: "#ffffff",
   legendTitleAsseLeftOffset: -50
 }
 
 
 return (
   <div>
     <div className="row ml-2 " > 
     <ManufacturerSelect   />
        <div class="w-100 border-primary  border-bottom"></div>
     </div>
     
     <div className="row ml-2 " > 
     <div class="col-lg-12"></div>
         <div className="col-lg-1 " >
            <h4> Manufacturer</h4>
          </div>
         
          <div className="col-lg-3 ml-4" >
            <h4> Component Count </h4>
          </div>
          <div class="w-100 border-primary  border-bottom"></div>

          <div className="col-lg-5" >
             {manufacturerList}
          </div>
   
        <div className="col-lg-7" >
        <BarChart points = {points} legends = {legends} title = {title} height = {height} legend = {legend}/>
        </div>
  
    </div>
  

</div>
  );
  
}


const mapState = (state) => ({
  count: state.dashboard.count,
  allBlock: state.dashboard.allBlock,
  countBlockType : state.dashboard.countBlockType,
  minManufacturerCount: state.dashboard.minManufacturerCount,
  
})

const mapDispatch = (dispatch, payload) => ({
  increment: (payload) => dispatch.dashboard.increment(payload),
  incrementAsync: () => dispatch.dashboard.incrementAsync(payload),
  loadAllBlock: (payload) => dispatch.dashboard.loadAllBlock(payload),
  loadCountBlockType: (payload) => dispatch.dashboard.loadCountBlockType(payload),
})


export default connect(mapState, mapDispatch)(ManufacturerList)


