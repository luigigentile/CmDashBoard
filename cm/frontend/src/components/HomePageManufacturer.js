import React from 'react';
import { Provider  } from 'react-redux'
import store from '../store'
import ManufacturerList from './ManufacturerList'

export default function HomePageManufacturer(props) {

  //      <div>
  //
  // </div>
  return (
    <div>
      <Provider store={store}>
           <ManufacturerList />
     </Provider>
      </div>
     
    );
  }
   
  
 
  