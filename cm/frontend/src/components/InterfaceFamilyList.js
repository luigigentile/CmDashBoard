import React from 'react';

import {useQuery} from "@apollo/client";
import {connect } from 'react-redux'
import {ALL_INTERFACE_FAMILY} from '../graphql'
import InterfaceFamilyItem from './InterfaceFamilyItem'
import BarChart from './chart/BarChart'

function InterfaceFamilyList(props) {

const { loading, error,  data:allInterfaceFamily } = useQuery(ALL_INTERFACE_FAMILY);
if (loading) return <p>Loading...</p>;
if (error) return <p>Errore nel caricare la pagina  :</p>;

let interfacesFamily = allInterfaceFamily.allInterfaceFamily

    const interfacesFamilyList = interfacesFamily.map((x) => {
      return (
     <InterfaceFamilyItem key = {x.id} interfaceFamily = {x}  /> 
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
  for (var i=0;i<interfacesFamily.length; i++) {
    point = {}
    point.Etichette = interfacesFamily[i].label
    point.Valori = interfacesFamily[i].interfaceTypeCount
    point.color = "hsl(92, 70%, 50%)"
    points.push(point)
  }
  
  var title =  "Interface Family Vs Interface Type "
  var height = 800
  var legend = {
    titleAsseX : "ManuFamily Type",
    titleAsseY : "Types' Component"
  }

return (
  <div>
     <div className="row ml-2 " > 
          <div className="col-lg-1" >
            <h4> Family</h4>
          </div>
         
          <div className="col-lg-3 ml-4" >
            <h4> Type Component  </h4>
          </div>
  
             <div className="w-100 border-primary  border-bottom"></div>
   
             <div className="col-lg-5" >
                {interfacesFamilyList}
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
  
})

const mapDispatch = (dispatch, payload) => ({
  increment: (payload) => dispatch.dashboard.increment(payload),
  incrementAsync: () => dispatch.dashboard.incrementAsync(payload),
  loadAllBlock: (payload) => dispatch.dashboard.loadAllBlock(payload),
  loadCountBlockType: (payload) => dispatch.dashboard.loadCountBlockType(payload),
})


export default connect(mapState, mapDispatch)(InterfaceFamilyList)


