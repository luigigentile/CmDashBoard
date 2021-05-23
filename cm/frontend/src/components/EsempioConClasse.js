import React, { useState,useEffect } from 'react';

class Child extends React.Component {
    constructor(props) {
     alert("Child - constructor");
     super(props);
    }
    componentWillMount() {
     alert("Child - ComponentWillMount");
    }
    componentDidMount() {
     alert("Child - ComponentDidMount");
    }
    componentWillReceiveProps(nextProps) {
     alert("Child - componentWillReceiveProps");
    }
    shouldComponentUpdate(nextProps, nextState) {
     alert("Child - ShouldComponentUpdate");
     return true;
    }
    componentWillUpdate(nextProps, nextState) {
     alert("Child - componentWillUpdate");
    }
    componentDidUpdate(nextProps, nextState) {
     alert("Child - componentDidUpdate");
    }
    componentWillUnmount() {
     alert("Child - componentWillUnmount");
    }
    render() {
     alert("Child - Render");
     return(
      <h1>{this.props.counter}</h1>
     );
    }
   }
   
   export default class EsempioConCLasse extends React.Component {
    constructor(props) {
     alert("App - constructor");
     super(props);
         this.state = {counter: 0, child: true};
    }
   
    increment() {
     this.setState((prevState, props) => ({
       counter: prevState.counter + 1
      })
     );
    }
    // aggiungiamo un metodo unmount()
    unmount() {
     this.setState({child: false});
    }
   
    // aggiungiamo un metodo mount()
    mount() {
     this.setState({child: true});
    }
   
    componentWillMount() {
     alert("App - ComponentWillMount");
     this.setState({counter: 1});
    }
    componentDidMount() {
     alert("App - ComponentDidMount");
   
    }
    shouldComponentUpdate(nextProps, nextState) {
     alert("App - ShouldComponentUpdate");
     return true;
    }
    componentWillUpdate(nextProps, nextState) {
     alert("App - componentWillUpdate");
    }
    componentDidUpdate(nextProps, nextState) {
     alert("App - componentDidUpdate");
    }
    render() {
     alert("App - Render");
   
     let child = null;
   
     /* se this.state.child è true, assegniamo alla variabile child
     *  il React Element <Child />
     */
     child = this.state.child ? <Child counter={this.state.counter} /> : null;
   
     return(
      <div>
       {child}
       <button onClick={() => this.increment()}>Increment</button>
       <button onClick={() => this.unmount()}>Unmount Child Component</button>
       <button onClick={() => this.mount()}>Mount Child Component</button>
      </div>
     );
    }
   }
   