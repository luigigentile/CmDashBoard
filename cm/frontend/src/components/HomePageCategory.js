import React from 'react';
import { Provider  } from 'react-redux'
import store from '../store'
import Category from './Category'

export default function HomePageCategory(props) {
     
      return (
     <div className = "ml-2">
        <Provider store={store}>
          <Category   />
        </Provider>
  </div>
  );
  
}
