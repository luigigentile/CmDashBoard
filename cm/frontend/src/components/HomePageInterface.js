import React from 'react';
import { Provider  } from 'react-redux'
import store from '../store'
import InterfaceFamilyList from './InterfaceFamilyList'

export default function HomePageInterface(props) {

  //      <div>
  //
  // </div>
  return (
    <div>
      <Provider store={store}>
           <InterfaceFamilyList />
     </Provider>
      </div>
     
    );
  }
   
  
 
  