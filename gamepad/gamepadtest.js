window.addEventListener('gamepadconnected', (event) => {
  const update = () => {
    let gamepadObj = {};
    let axes = [];
    gamepadObj.axes = axes;
    console.log(gamepadObj);
     for (const gamepad of navigator.getGamepads()) {
     if (!gamepad) continue;
        for (const [index, axis] of gamepad.axes.entries()) {
            let value= (axis * 0.5 + 0.5)
            let axle = {
            index,
            value
            };
            gamepadObj.axes.push(axle);
      }
    }
    requestAnimationFrame(update);
  };
  update();
});


// https://www.javascripture.com/Gamepad 
//window.addEventListener('gamepadconnected', (event) => {
//  const update = () => {
//    const output = document.getElementById('axes');
//    output.innerHTML = ''; // clear the output
//
//    for (const gamepad of navigator.getGamepads()) {
//      if (!gamepad) continue;
//      for (const [index, axis] of gamepad.axes.entries()) {
//        output.insertAdjacentHTML('beforeend',
//             `<label>${index}
//             value=${axis * 0.5 + 0.5}
//           </label>`);
//      }
//    }
//    requestAnimationFrame(update);
//  };
//  update();
//});


//Press button on controller to connect.
//<div id="buttons" style="display: flex; flex-direction: column;"></div>
//<script>
//window.addEventListener('gamepadconnected', (event) => {
//  const update = () => {
//    const output = document.getElementById('buttons');
//    output.innerHTML = ''; // clear the output
//
//    for (const gamepad of navigator.getGamepads()) {
//      if (!gamepad) continue;
//      for (const [index, button] of gamepad.buttons.entries()) {
//        output.insertAdjacentHTML('beforeend',
//          `<label>${gamepad.index}, ${index}
//             <progress value=${button.value}></progress>
//             ${button.touched ? 'touched' : ''}
//             ${button.pressed ? 'pressed' : ''}
//           </label>`);
//      }
//    }
//    requestAnimationFrame(update);
//  };
//  update();
//});
//</script>
