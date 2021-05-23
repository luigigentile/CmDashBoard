import React from 'react';
import { Provider  } from 'react-redux'
import store from '../store'
import BlockComponent from './BlockComponent'


export default function HomePageComponent(props) {



    return (
      <div>
        <h2> COMPONENTS</h2>
      <div>
        <Provider store={store}>
        <BlockComponent />
        </Provider>
      </div>
      </div>
     
    );
  }
   
  
 
  