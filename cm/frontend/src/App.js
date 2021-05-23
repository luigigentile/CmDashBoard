import React, { Component } from 'react'
import { BrowserRouter as Router, Route,  Link } from 'react-router-dom'
import {  ApolloProvider,} from "@apollo/client";
import logocm from './staticfiles/CMLogotrans.png';
import logocm1 from './staticfiles/small-left.svg';

import client from './client'

import HomePage from './components/HomePage'
import HomePageComponent from './components/HomePageComponent'
import HomePageCategory from './components/HomePageCategory'
import HomePageManufacturer from './components/HomePageManufacturer'
import HomePageInterface from './components/HomePageInterface'
import HomePageProve from './components/HomePageProve'




class App extends Component {
  
  render() {
    // alert(React.version);

    return (
      <div 
       style={{
        backgroundColor: "#061D36",
        color:"white"
        }}
          
        >
      
      <ApolloProvider client={client} >
        <Router>
          <div
   
        >
      
        {/* NAV BAR  
          <nav className="navbar navbar-expand-sm navbar-light bg-light my-navbar bg-primary " >
          */}  
          <nav className="navbar navbar-expand-lg navbar-light bg-light">
        {/* HOME PAGE  */}  
          <Link className="navbar-brand btn btn-sm " to="/">
              <img src={logocm} width="30" height="30" className="icon-delete" alt="logo" />
              <img src={logocm1} width="30" height="30" className="icon-delete" alt="logo" />
          </Link>
         <Link className="navbar-brand btn btn-sm " to="/">Home Page</Link>
         <Link className="navbar-brand" to="/Component">Component</Link>
         <Link className="navbar-brand" to="/Category">Category</Link>
         <Link className="navbar-brand" to="/Manufacturer">Manufacturer  </Link>  
         <Link className="navbar-brand" to="/Interface">Interface  </Link>
         <Link className="navbar-brand" to="/Prove">Prove</Link> 

          </nav>

          <Route exact path="/" component={HomePage} />                
          <Route exact path="/Component" component={HomePageComponent} />
          <Route exact path="/Category" component={HomePageCategory} />
          <Route path="/Manufacturer" component={HomePageManufacturer}  />
          <Route path="/Interface" component={HomePageInterface}  />
          <Route path="/Prove" component={HomePageProve}  />
      
      
        
            {/* fine menu drop down 
          <Link className="navbar-brand" to="/esempio1/">esempio con Classe</Link> 
          <Link className="navbar-brand" to="/BlockList">Block List</Link>
          <Link className="navbar-brand"to="/logout/">Logout</Link>
          <Route path="/esempio1/" component={EsempioConClasse}  />
        

          <Route exact path="/BlockList" component={BlockManage} />
          <Route  exact path="/messages/delete/:id/" component={DeleteView} />
          <Route exact path="/nivoline/" component={NivoLine} />      
        
        
            */}
        </div>
      </Router>
      </ApolloProvider>
      </div>
    
    
    )
  }
}

 export default App
